# Task 21: Multi-Stream Schema Migration

## Goal

Enable multiple independent streams with separate RSS feeds, per-stream deduplication, and optimized partitioning. Rename `us_close_basic` → `us_close`.

## Background

Currently, all news is ingested into a shared pool. To support multiple streams (e.g., `us_close`, `asia_markets`, `crypto_daily`) with different RSS sources, we need:

1. Per-stream news storage and deduplication
2. Partition key change from `(ingested_at)` to `(stream_name, ingested_at)` for query performance
3. Config restructure to define streams at top-level

## Scope

### Database Migration (`002_multi_stream_schema.sql`)

| Table | Change |
|-------|--------|
| `news_fingerprints` | Add `stream_name`, update unique constraint |
| `news_items` | Recreate with `PARTITION BY LIST (stream_name)` then `RANGE (ingested_at)` |
| `news_scores` | Add `stream_name` |
| `news_content` | Add `stream_name` |
| `runs` | Update existing `us_close_basic` → `us_close` |
| `telegram_stream_subscriptions` | Update existing `us_close_basic` → `us_close` |

### Partition Naming Convention

- Old: `news_items_2026_01_08`
- New: `news_items_us_close_2026_01_08`

### Config Restructure (`config.yaml`)

**Before:**
```yaml
stream:
  name: us_close_basic
  enabled: true

rss:
  allowlist_files:
    - "rss/us_close_basic.txt"
```

**After:**
```yaml
streams:
  us_close:
    enabled: true
    rss_files:
      - "rss/us_close.txt"
```

### File Renames

| Old | New |
|-----|-----|
| `rss/us_close_basic.txt` | `rss/us_close.txt` |

### Code Changes

| File | Change |
|------|--------|
| `src/argus/db/partitions.py` | Update `create_news_items_partition()` to accept `stream_name` |
| `src/argus/db/repository.py` | Add `stream_name` param to insert/query functions |
| `src/argus/ingestion/worker.py` | Pass `stream_name` to repository |
| `src/argus/config/providers.py` | Parse new `streams:` config structure |
| `src/argus/facts_bundle/builder.py` | Update default stream name |
| `src/argus/cli.py` | Update `--stream` default if any |

### Renames: `us_close_basic` → `us_close`

#### Database (handled in migration)
- `runs.stream_name`
- `telegram_stream_subscriptions.stream_name`
- `news_fingerprints.stream_name` (new column, backfilled as `us_close`)
- `news_items.stream_name` (new column, backfilled as `us_close`)
- `news_scores.stream_name` (new column, backfilled as `us_close`)
- `news_content.stream_name` (new column, backfilled as `us_close`)

#### Config Files
- `config.yaml` — stream name and structure
- `rss/us_close_basic.txt` → `rss/us_close.txt`

#### Source Code
| File | Lines to Update |
|------|-----------------|
| `src/argus/facts_bundle/builder.py:46` | Default `stream_name = "us_close_basic"` |
| `src/argus/config/providers.py` | Config parsing logic |

#### Tests & Fixtures
| File | Change |
|------|--------|
| `tests/fixtures/facts_bundle.json:3` | `"stream_name": "us_close_basic"` → `"us_close"` |
| `tests/test_config_providers.py:24,27,45` | YAML fixtures and assertions |
| `tests/test_generator.py:153` | `stream_name="us_close_basic"` |
| `tests/test_db_models.py:139,155` | Stream name in test data |
| `tests/test_facts_bundle.py:112,329,342` | Stream name assertions |

#### Documentation (update references, no functional impact)
- `tasks/01_plan/spec.md` — multiple references
- `docs/archived/rss_feed_research_report.md`
- Archived task docs in `tasks/03_archive/`

---

## Migration SQL

```sql
-- 002_multi_stream_schema.sql
-- Multi-stream support: per-stream news with (stream_name, ingested_at) partitioning

BEGIN;

-- ============================================================================
-- 1. Add stream_name to news_fingerprints
-- ============================================================================
ALTER TABLE news_fingerprints 
  ADD COLUMN stream_name VARCHAR(100);

-- Backfill existing data
UPDATE news_fingerprints SET stream_name = 'us_close' WHERE stream_name IS NULL;

-- Make NOT NULL after backfill
ALTER TABLE news_fingerprints 
  ALTER COLUMN stream_name SET NOT NULL;

-- Update unique constraint to be per-stream
ALTER TABLE news_fingerprints 
  DROP CONSTRAINT IF EXISTS news_fingerprints_hash_url_key;
ALTER TABLE news_fingerprints 
  ADD CONSTRAINT news_fingerprints_stream_hash_url_key UNIQUE (stream_name, hash_url);

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
-- Create stream-level partition for us_close (sub-partitioned by date)
CREATE TABLE news_items_us_close PARTITION OF news_items_new
    FOR VALUES IN ('us_close')
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
        
        -- Create new sub-partition under us_close
        new_partition_name := 'news_items_us_close_' || to_char(partition_date, 'YYYY_MM_DD');
        
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I PARTITION OF news_items_us_close
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
            'us_close',
            old_partition.partition_name
        );
    END LOOP;
END $$;

-- ============================================================================
-- 4. Drop old table, rename new
-- ============================================================================
DROP TABLE news_items CASCADE;
ALTER TABLE news_items_new RENAME TO news_items;

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
ALTER TABLE news_scores ADD COLUMN stream_name VARCHAR(100);
UPDATE news_scores SET stream_name = 'us_close' WHERE stream_name IS NULL;
ALTER TABLE news_scores ALTER COLUMN stream_name SET NOT NULL;
CREATE INDEX idx_news_scores_stream ON news_scores(stream_name);

-- ============================================================================
-- 6. Add stream_name to news_content
-- ============================================================================
ALTER TABLE news_content ADD COLUMN stream_name VARCHAR(100);
UPDATE news_content SET stream_name = 'us_close' WHERE stream_name IS NULL;
ALTER TABLE news_content ALTER COLUMN stream_name SET NOT NULL;
CREATE INDEX idx_news_content_stream ON news_content(stream_name);

-- ============================================================================
-- 7. Rename stream: us_close_basic → us_close
-- ============================================================================
UPDATE runs SET stream_name = 'us_close' WHERE stream_name = 'us_close_basic';
UPDATE telegram_stream_subscriptions SET stream_name = 'us_close' WHERE stream_name = 'us_close_basic';

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
INSERT INTO schema_migrations (version) VALUES ('002_multi_stream_schema');

COMMIT;
```

---

## Execution Plan

### Pre-Migration (Off-Hours)

1. **Stop daemon**
   ```bash
   systemctl stop argus
   ```

2. **Backup database**
   ```bash
   pg_dump $DATABASE_URL > argus_backup_$(date +%Y%m%d_%H%M%S).sql
   ```

3. **Verify current state**
   ```bash
   argus db status
   ```

### Run Migration

4. **Apply migration**
   ```bash
   argus db migrate
   ```

5. **Verify migration**
   ```sql
   -- Check new partitions exist
   SELECT c.relname FROM pg_class c 
   JOIN pg_inherits i ON c.oid = i.inhrelid 
   WHERE c.relname LIKE 'news_items_%' ORDER BY c.relname;
   
   -- Check data count matches (should be 476)
   SELECT COUNT(*) FROM news_items;
   
   -- Check stream_name populated
   SELECT DISTINCT stream_name FROM news_items;
   SELECT DISTINCT stream_name FROM news_fingerprints;
   ```

### Update Config & Files

6. **Rename RSS file**
   ```bash
   git mv rss/us_close_basic.txt rss/us_close.txt
   ```

7. **Update config.yaml** — apply new structure

8. **Update source code** — all files listed in Code Changes section

9. **Update tests & fixtures**

### Test

10. **Run smoke test**
    ```bash
    argus smoke --verbose
    ```

11. **Test ingest (dry-run)**
    ```bash
    argus ingest --stream us_close --dry-run
    ```

12. **Run full test suite**
    ```bash
    pytest
    ```

### Deploy

13. **Commit changes**
    ```bash
    git add -A
    git commit -m "feat: multi-stream schema with per-stream partitioning"
    ```

14. **Restart daemon**
    ```bash
    systemctl start argus
    ```

15. **Verify daemon health**
    ```bash
    argus daemon status
    ```

---

## What Could Go Wrong

### Migration Failures

| Failure Mode | Symptom | Recovery |
|--------------|---------|----------|
| **CASCADE drops too much** | `DROP TABLE news_items CASCADE` removes dependent views/FKs unexpectedly | Restore from backup; audit all FKs before migration |
| **Partition creation fails** | `CREATE TABLE ... PARTITION OF` errors (constraint overlap, naming) | Transaction rolls back; fix SQL and retry |
| **Data type mismatch** | INSERT into new table fails on type incompatibility | Shouldn't happen (same schema), but check column order |
| **Sequence not reset** | New inserts get duplicate IDs | `SELECT setval('news_items_id_seq', (SELECT MAX(id) FROM news_items))` |
| **Index creation fails** | OOM or timeout on large tables | Not an issue with 476 rows; would be for millions |

### Post-Migration Issues

| Failure Mode | Symptom | Recovery |
|--------------|---------|----------|
| **Old function signature called** | `create_news_items_partition(DATE)` fails (dropped) | Code still using old signature; grep and fix |
| **Missing stream partition** | Insert fails: "no partition for value 'asia_markets'" | `create_news_items_partition('asia_markets', CURRENT_DATE)` |
| **Config parsing fails** | Argus won't start; `KeyError` on `stream.name` | Code still expects old config structure; update providers.py |
| **Test fixtures stale** | Tests fail on `us_close_basic` assertions | Update all fixtures before running tests |
| **Hardcoded stream names** | Various failures in code paths | Grep for `us_close_basic` to find all references |

### Runtime Issues (After Deploy)

| Failure Mode | Symptom | Recovery |
|--------------|---------|----------|
| **Partition pruning not working** | Queries slow (scanning all partitions) | Check `EXPLAIN` output; ensure `stream_name` in WHERE clause |
| **Dedupe fails cross-stream** | Same URL rejected in different stream | Check unique constraint is `(stream_name, hash_url)` not just `(hash_url)` |
| **Retention drops wrong partitions** | Old data persists or new data deleted | Test `drop_old_news_items_partitions()` manually first |
| **Telegram subscriptions broken** | Messages not delivered | Check `telegram_stream_subscriptions` has `us_close` not `us_close_basic` |

### Rollback Plan

If migration fails mid-way:
1. Transaction should auto-rollback (entire migration is in `BEGIN/COMMIT`)
2. If partial state, restore from backup:
   ```bash
   psql $DATABASE_URL < argus_backup_YYYYMMDD_HHMMSS.sql
   ```

If issues found after deploy:
1. Stop daemon
2. Revert code: `git revert HEAD`
3. Restore database from backup
4. Restart daemon with old code

---

## Acceptance Criteria

- [ ] Migration applies cleanly with no data loss
- [ ] All 476 existing news items migrated to `us_close` stream
- [ ] Partition naming follows `news_items_{stream}_{date}` pattern
- [ ] New partition function accepts `(stream_name, date)` signature
- [ ] `argus ingest --stream us_close` works with new schema
- [ ] `argus ingest --stream asia_markets` creates new stream partitions automatically
- [ ] Deduplication is per-stream (same URL can exist in multiple streams)
- [ ] All tests pass
- [ ] No references to `us_close_basic` remain in codebase (except archived docs)
- [ ] `grep -r "us_close_basic" src/ tests/ config.yaml rss/` returns empty

---

## Dependencies

- None (standalone migration)

## Estimated Effort

- Migration SQL: 1-2 hours (testing, edge cases)
- Code changes: 2-3 hours
- Test updates: 1 hour
- Deployment: 30 min (off-hours)

**Total: ~5-6 hours**
