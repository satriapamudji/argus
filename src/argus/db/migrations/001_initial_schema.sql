-- Migration: 001_initial_schema
-- Description: Create initial database schema for Argus
-- Date: 2026-01-07

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Schema migrations tracking table
CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(255) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- news_fingerprints: Long-lived fingerprints for deduplication
-- Retained 1-10 years (configurable). Survives news_items partition drops.
-- ============================================================================
CREATE TABLE news_fingerprints (
    id BIGSERIAL PRIMARY KEY,
    hash_url VARCHAR(64) NOT NULL,  -- sha256 hex of normalized URL
    hash_text VARCHAR(64),          -- sha256 hex of normalized title + snippet
    simhash BIGINT,                 -- 64-bit SimHash signature
    source_name VARCHAR(255) NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Unique constraint on hash_url for exact URL deduplication
CREATE UNIQUE INDEX idx_fingerprints_hash_url ON news_fingerprints(hash_url);

-- Index for text hash lookups
CREATE INDEX idx_fingerprints_hash_text ON news_fingerprints(hash_text) 
    WHERE hash_text IS NOT NULL;

-- Index for SimHash near-duplicate lookups (used with Hamming distance check)
CREATE INDEX idx_fingerprints_simhash ON news_fingerprints(simhash) 
    WHERE simhash IS NOT NULL;

-- Index for source lookups
CREATE INDEX idx_fingerprints_source ON news_fingerprints(source_name);

-- ============================================================================
-- news_items: Partitioned table for news metadata
-- Partitioned by day on ingested_at. Retained 60 days by default.
-- ============================================================================
CREATE TABLE news_items (
    id BIGSERIAL,
    fingerprint_id BIGINT NOT NULL REFERENCES news_fingerprints(id),
    source_name VARCHAR(255) NOT NULL,
    source_url TEXT NOT NULL,
    title TEXT NOT NULL,
    snippet TEXT,
    author VARCHAR(255),
    published_at TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    raw_metadata JSONB,
    PRIMARY KEY (id, ingested_at)
) PARTITION BY RANGE (ingested_at);

-- Index for fingerprint lookups
CREATE INDEX idx_news_items_fingerprint ON news_items(fingerprint_id);

-- Index for published_at queries
CREATE INDEX idx_news_items_published ON news_items(published_at) 
    WHERE published_at IS NOT NULL;

-- Index for source queries
CREATE INDEX idx_news_items_source ON news_items(source_name);

-- pg_trgm index for title similarity searches
CREATE INDEX idx_news_items_title_trgm ON news_items 
    USING gin(title gin_trgm_ops);

-- ============================================================================
-- news_content: Optional full text / excerpt storage
-- Linked to news_items; follows same retention policy.
-- ============================================================================
CREATE TABLE news_content (
    id BIGSERIAL PRIMARY KEY,
    news_item_id BIGINT NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,  -- Denormalized for partition pruning
    content_type VARCHAR(20) NOT NULL CHECK (content_type IN ('excerpt', 'full_text')),
    content TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,  -- sha256 hex
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    content_status VARCHAR(20) NOT NULL DEFAULT 'pending' 
        CHECK (content_status IN ('success', 'failed', 'pending'))
);

-- Index for news_item lookups
CREATE INDEX idx_news_content_item ON news_content(news_item_id);

-- ============================================================================
-- news_scores: Scoring results from heuristics and/or LLM triage
-- ============================================================================
CREATE TABLE news_scores (
    id BIGSERIAL PRIMARY KEY,
    news_item_id BIGINT NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,  -- Denormalized for partition pruning
    impact_score SMALLINT NOT NULL CHECK (impact_score >= 0 AND impact_score <= 100),
    quality_score SMALLINT NOT NULL CHECK (quality_score >= 0 AND quality_score <= 100),
    confidence_score SMALLINT NOT NULL CHECK (confidence_score >= 0 AND confidence_score <= 100),
    topic VARCHAR(50),
    flags JSONB,      -- Array of flags, e.g., ["breaking", "earnings"]
    reasons JSONB,    -- Array of scoring reasons
    scored_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    scorer_version VARCHAR(50) NOT NULL DEFAULT 'v1'
);

-- Index for news_item lookups
CREATE INDEX idx_news_scores_item ON news_scores(news_item_id);

-- Index for high-impact items
CREATE INDEX idx_news_scores_impact ON news_scores(impact_score DESC);

-- Index for topic filtering
CREATE INDEX idx_news_scores_topic ON news_scores(topic) WHERE topic IS NOT NULL;

-- ============================================================================
-- runs: Run orchestration and artifacts
-- Stores facts bundle, timings, and monday_preview risk breakdown.
-- ============================================================================
CREATE TABLE runs (
    id BIGSERIAL PRIMARY KEY,
    stream_name VARCHAR(100) NOT NULL,
    run_mode VARCHAR(50) NOT NULL CHECK (run_mode IN ('us_close', 'weekend_wrap', 'monday_preview')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'pending' 
        CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    facts_bundle_json JSONB,
    timings_json JSONB,
    -- Monday preview risk breakdown (nullable for other modes)
    risk_score SMALLINT CHECK (risk_score IS NULL OR (risk_score >= 0 AND risk_score <= 100)),
    calendar_score SMALLINT CHECK (calendar_score IS NULL OR (calendar_score >= 0 AND calendar_score <= 100)),
    market_score SMALLINT CHECK (market_score IS NULL OR (market_score >= 0 AND market_score <= 100)),
    headline_score SMALLINT CHECK (headline_score IS NULL OR (headline_score >= 0 AND headline_score <= 100)),
    error_message TEXT
);

-- Index for stream + mode queries
CREATE INDEX idx_runs_stream_mode ON runs(stream_name, run_mode);

-- Index for status queries
CREATE INDEX idx_runs_status ON runs(status);

-- Index for time-based queries
CREATE INDEX idx_runs_started ON runs(started_at DESC);

-- ============================================================================
-- messages: Generated messages with validation and publish status
-- ============================================================================
CREATE TABLE messages (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    validation_status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (validation_status IN ('pending', 'valid', 'invalid', 'fallback')),
    validation_errors JSONB,  -- Array of error messages
    publish_status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (publish_status IN ('pending', 'published', 'failed', 'skipped')),
    telegram_message_id BIGINT,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for run lookups
CREATE INDEX idx_messages_run ON messages(run_id);

-- Index for publish status queries
CREATE INDEX idx_messages_publish_status ON messages(publish_status);

-- ============================================================================
-- Partition management: Function to create daily partitions
-- ============================================================================
CREATE OR REPLACE FUNCTION create_news_items_partition(partition_date DATE)
RETURNS TEXT AS $$
DECLARE
    partition_name TEXT;
    start_date DATE;
    end_date DATE;
BEGIN
    partition_name := 'news_items_' || to_char(partition_date, 'YYYY_MM_DD');
    start_date := partition_date;
    end_date := partition_date + INTERVAL '1 day';
    
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF news_items 
         FOR VALUES FROM (%L) TO (%L)',
        partition_name,
        start_date,
        end_date
    );
    
    RETURN partition_name;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Partition management: Function to drop old partitions for retention
-- ============================================================================
CREATE OR REPLACE FUNCTION drop_old_news_items_partitions(retention_days INTEGER)
RETURNS TABLE(dropped_partition TEXT) AS $$
DECLARE
    partition_record RECORD;
    cutoff_date DATE;
BEGIN
    cutoff_date := CURRENT_DATE - (retention_days || ' days')::INTERVAL;
    
    FOR partition_record IN
        SELECT c.relname AS partition_name
        FROM pg_class c
        JOIN pg_inherits i ON c.oid = i.inhrelid
        JOIN pg_class parent ON parent.oid = i.inhparent
        WHERE parent.relname = 'news_items'
        AND c.relname ~ '^news_items_\d{4}_\d{2}_\d{2}$'
    LOOP
        -- Extract date from partition name and check if it's old enough
        IF to_date(
            substring(partition_record.partition_name FROM 'news_items_(\d{4}_\d{2}_\d{2})'),
            'YYYY_MM_DD'
        ) < cutoff_date THEN
            EXECUTE format('DROP TABLE IF EXISTS %I', partition_record.partition_name);
            dropped_partition := partition_record.partition_name;
            RETURN NEXT;
        END IF;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Create initial partition for today to allow immediate inserts
-- ============================================================================
SELECT create_news_items_partition(CURRENT_DATE);

-- Record this migration
INSERT INTO schema_migrations (version) VALUES ('001_initial_schema');
