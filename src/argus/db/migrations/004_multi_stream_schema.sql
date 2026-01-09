-- Migration: 004_multi_stream_schema
-- Description: Multi-stream support with per-stream news partitioning
-- Date: 2026-01-09
--
-- BREAKING CHANGE: This migration recreates news_items with a new partition scheme.
-- All existing data is migrated to the 'us_markets' stream.
--
-- Changes:
-- 1. Add stream_name to news_fingerprints (per-stream deduplication)
-- 2. Recreate news_items with PARTITION BY LIST (stream_name) then RANGE (ingested_at)
-- 3. Add stream_name to news_scores and news_content
-- 4. Rename stream: us_markets_basic → us_markets in runs and telegram_stream_subscriptions
-- 5. Update partition management functions to accept stream_name

BEGIN;

-- ============================================================================
-- 1. Add stream_name to news_fingerprints
-- ============================================================================
ALTER TABLE news_fingerprints 
  ADD COLUMN IF NOT EXISTS stream_name VARCHAR(100);

-- Backfill existing data
UPDATE news_fingerprints SET stream_name = 'us_markets' WHERE stream_name IS NULL;

-- Make NOT NULL after backfill
ALTER TABLE news_fingerprints 
  ALTER COLUMN stream_name SET NOT NULL;

-- Update unique constraint to be per-stream
ALTER TABLE news_fingerprints 
  DROP CONSTRAINT IF EXISTS news_fingerprints_hash_url_key;
DROP INDEX IF EXISTS idx_fingerprints_hash_url;
ALTER TABLE news_fingerprints 
  ADD CONSTRAINT news_fingerprints_stream_hash_url_key UNIQUE (stream_name, hash_url);

-- Add index for stream lookups
CREATE INDEX IF NOT EXISTS idx_fingerprints_stream ON news_fingerprints(stream_name);

-- ============================================================================
-- 2. Create new news_items with composite partition key
-- ============================================================================
CREATE TABLE news_items_new (
    id BIGSERIAL,
    stream_name VARCHAR(100) NOT NULL,
    fingerprint_id BIGINT NOT NULL REFERENCES news_fingerprints(id),
    source_name VARCHAR(255) NOT NULL,
    source_url TEXT NOT NULL,
    title TEXT NOT NULL,
    snippet TEXT,
    author VARCHAR(255),
    published_at TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    raw_metadata JSONB,
    PRIMARY KEY (id, stream_name, ingested_at)
) PARTITION BY LIST (stream_name);

-- ============================================================================
-- 3. Migrate existing data
-- ============================================================================
-- Create stream-level partition for us_markets (sub-partitioned by date)
CREATE TABLE news_items_us_markets PARTITION OF news_items_new
    FOR VALUES IN ('us_markets')
    PARTITION BY RANGE (ingested_at);

-- Create daily sub-partitions and migrate data from old partitions
DO $$
DECLARE
    old_partition RECORD;
    new_partition_name TEXT;
    partition_date DATE;
BEGIN
    FOR old_partition IN
        SELECT c.relname AS partition_name
        FROM pg_class c
        JOIN pg_inherits i ON c.oid = i.inhrelid
        JOIN pg_class parent ON parent.oid = i.inhparent
        WHERE parent.relname = 'news_items'
        AND c.relname ~ '^news_items_\d{4}_\d{2}_\d{2}$'
        ORDER BY c.relname
    LOOP
        -- Extract date from old partition name
        partition_date := to_date(
            substring(old_partition.partition_name FROM 'news_items_(\d{4}_\d{2}_\d{2})'),
            'YYYY_MM_DD'
        );
        
        -- Create new sub-partition under us_markets
        new_partition_name := 'news_items_us_markets_' || to_char(partition_date, 'YYYY_MM_DD');
        
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I PARTITION OF news_items_us_markets
             FOR VALUES FROM (%L) TO (%L)',
            new_partition_name,
            partition_date,
            partition_date + INTERVAL '1 day'
        );
        
        -- Migrate data from old partition to new
        EXECUTE format(
            'INSERT INTO %I (id, stream_name, fingerprint_id, source_name, source_url, 
                            title, snippet, author, published_at, ingested_at, raw_metadata)
             SELECT id, %L, fingerprint_id, source_name, source_url,
                    title, snippet, author, published_at, ingested_at, raw_metadata
             FROM %I',
            new_partition_name,
            'us_markets',
            old_partition.partition_name
        );
    END LOOP;
END $$;

-- ============================================================================
-- 4. Drop old table, rename new
-- ============================================================================
DROP TABLE news_items CASCADE;
ALTER TABLE news_items_new RENAME TO news_items;

-- Reset sequence to max id + 1
SELECT setval('news_items_new_id_seq', COALESCE((SELECT MAX(id) FROM news_items), 0) + 1, false);
ALTER SEQUENCE news_items_new_id_seq RENAME TO news_items_id_seq;

-- Recreate indexes on new table
CREATE INDEX idx_news_items_fingerprint ON news_items(fingerprint_id);
CREATE INDEX idx_news_items_published ON news_items(published_at) 
    WHERE published_at IS NOT NULL;
CREATE INDEX idx_news_items_source ON news_items(source_name);
CREATE INDEX idx_news_items_stream ON news_items(stream_name);
CREATE INDEX idx_news_items_title_trgm ON news_items 
    USING gin(title gin_trgm_ops);

-- ============================================================================
-- 5. Add stream_name to news_scores
-- ============================================================================
ALTER TABLE news_scores ADD COLUMN IF NOT EXISTS stream_name VARCHAR(100);
UPDATE news_scores SET stream_name = 'us_markets' WHERE stream_name IS NULL;
ALTER TABLE news_scores ALTER COLUMN stream_name SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_news_scores_stream ON news_scores(stream_name);

-- ============================================================================
-- 6. Add stream_name to news_content
-- ============================================================================
ALTER TABLE news_content ADD COLUMN IF NOT EXISTS stream_name VARCHAR(100);
UPDATE news_content SET stream_name = 'us_markets' WHERE stream_name IS NULL;
ALTER TABLE news_content ALTER COLUMN stream_name SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_news_content_stream ON news_content(stream_name);

-- ============================================================================
-- 7. Rename stream: us_close_basic → us_markets
-- ============================================================================
UPDATE runs SET stream_name = 'us_markets' WHERE stream_name = 'us_close_basic';
UPDATE telegram_stream_subscriptions SET stream_name = 'us_markets' WHERE stream_name = 'us_close_basic';

-- ============================================================================
-- 8. Update partition management functions
-- ============================================================================
DROP FUNCTION IF EXISTS create_news_items_partition(DATE);

CREATE OR REPLACE FUNCTION create_news_items_partition(p_stream_name TEXT, partition_date DATE)
RETURNS TEXT AS $$
DECLARE
    stream_partition_name TEXT;
    daily_partition_name TEXT;
    start_date DATE;
    end_date DATE;
BEGIN
    stream_partition_name := 'news_items_' || p_stream_name;
    daily_partition_name := stream_partition_name || '_' || to_char(partition_date, 'YYYY_MM_DD');
    start_date := partition_date;
    end_date := partition_date + INTERVAL '1 day';
    
    -- Ensure stream-level partition exists (LIST partition)
    BEGIN
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I PARTITION OF news_items
             FOR VALUES IN (%L)
             PARTITION BY RANGE (ingested_at)',
            stream_partition_name,
            p_stream_name
        );
    EXCEPTION WHEN duplicate_table THEN
        -- Stream partition already exists, continue
    END;
    
    -- Create daily sub-partition (RANGE partition)
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF %I
         FOR VALUES FROM (%L) TO (%L)',
        daily_partition_name,
        stream_partition_name,
        start_date,
        end_date
    );
    
    RETURN daily_partition_name;
END;
$$ LANGUAGE plpgsql;

DROP FUNCTION IF EXISTS drop_old_news_items_partitions(INTEGER);

CREATE OR REPLACE FUNCTION drop_old_news_items_partitions(retention_days INTEGER)
RETURNS TABLE(dropped_partition TEXT) AS $$
DECLARE
    partition_record RECORD;
    cutoff_date DATE;
    partition_date_str TEXT;
BEGIN
    cutoff_date := CURRENT_DATE - (retention_days || ' days')::INTERVAL;
    
    -- Find all daily sub-partitions (pattern: news_items_{stream}_{YYYY_MM_DD})
    FOR partition_record IN
        SELECT c.relname AS partition_name
        FROM pg_class c
        JOIN pg_inherits i ON c.oid = i.inhrelid
        WHERE c.relname ~ '^news_items_[a-z_]+_\d{4}_\d{2}_\d{2}$'
    LOOP
        -- Extract date from partition name (last 10 chars: YYYY_MM_DD)
        partition_date_str := substring(partition_record.partition_name FROM '\d{4}_\d{2}_\d{2}$');
        
        IF to_date(partition_date_str, 'YYYY_MM_DD') < cutoff_date THEN
            EXECUTE format('DROP TABLE IF EXISTS %I', partition_record.partition_name);
            dropped_partition := partition_record.partition_name;
            RETURN NEXT;
        END IF;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 9. Record migration
-- ============================================================================
INSERT INTO schema_migrations (version) VALUES ('004_multi_stream_schema');

COMMIT;
