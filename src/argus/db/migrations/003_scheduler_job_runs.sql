-- Migration: 003_scheduler_job_runs
-- Description: Create scheduler job runs table for daemon job history
-- Date: 2026-01-07

-- ============================================================================
-- scheduler_job_runs: Job execution history for the daemon scheduler
-- Tracks when jobs ran, their status, and any errors.
-- ============================================================================
CREATE TABLE scheduler_job_runs (
    id BIGSERIAL PRIMARY KEY,
    job_id VARCHAR(50) NOT NULL,           -- 'ingest', 'us_close', 'weekend_wrap', etc.
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL             -- 'running', 'success', 'failed'
        CHECK (status IN ('running', 'success', 'failed')),
    error_message TEXT,
    duration_ms INTEGER,
    
    -- Optional metadata
    run_id BIGINT,                          -- Reference to runs table if applicable
    trigger_type VARCHAR(20) DEFAULT 'scheduled'  -- 'scheduled', 'manual', 'catchup'
        CHECK (trigger_type IN ('scheduled', 'manual', 'catchup'))
);

-- Index for job status lookups (most recent runs per job)
CREATE INDEX idx_scheduler_job_runs_job_id 
    ON scheduler_job_runs(job_id, started_at DESC);

-- Index for finding running jobs (for health check)
CREATE INDEX idx_scheduler_job_runs_status 
    ON scheduler_job_runs(status) 
    WHERE status = 'running';

-- Index for general time-based queries
CREATE INDEX idx_scheduler_job_runs_started_at 
    ON scheduler_job_runs(started_at DESC);

-- Record this migration
INSERT INTO schema_migrations (version) VALUES ('003_scheduler_job_runs');
