-- Migration: 006_cu_optimization_indexes
-- Description: Add indexes to reduce CU usage for dedupe and cleanup queries
-- Date: 2026-01-12

BEGIN;

-- Index for text hash lookup (per-stream)
CREATE INDEX IF NOT EXISTS idx_fingerprints_stream_hash_text
ON news_fingerprints(stream_name, hash_text)
WHERE hash_text IS NOT NULL;

-- Index for near-duplicate window scans (per-stream)
CREATE INDEX IF NOT EXISTS idx_fingerprints_stream_first_seen
ON news_fingerprints(stream_name, first_seen_at)
WHERE simhash IS NOT NULL;

-- Index for fingerprint cleanup
CREATE INDEX IF NOT EXISTS idx_fingerprints_last_seen
ON news_fingerprints(last_seen_at);

-- Record migration
INSERT INTO schema_migrations (version) VALUES ('006_cu_optimization_indexes');

COMMIT;
