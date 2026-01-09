# Task 21: Multi-Stream Database Schema

## Summary
Added multi-stream support to the database schema with per-stream partitioning and deduplication. Renamed the default stream from `us_close_basic` to `us_markets`.

## Changes Made

### Database Migration (`004_multi_stream_schema.sql`)
- Added `stream_name` column to `news_fingerprints` table (with unique constraint per-stream)
- Added `stream_name` column to `news_items` table (partition key)
- Added `stream_name` column to `news_scores` and `news_content` tables
- Recreated `news_items` with composite partitioning: `PARTITION BY LIST (stream_name)` → sub-partitions by `RANGE (ingested_at)`
- Updated partition functions to accept `(stream_name, date)` signature
- Renamed existing data from `us_close_basic` → `us_markets` in `runs` and `telegram_stream_subscriptions`

### Code Changes
- **`src/argus/db/partitions.py`**: Updated all partition functions to accept `stream_name` parameter
- **`src/argus/db/repository.py`**: 
  - `get_or_create_fingerprint()` - added `stream_name` param
  - `insert_news_item()` - added `stream_name` param
  - `check_duplicate_by_url()` - added `stream_name` for per-stream deduplication
  - `check_duplicate_by_text()` - added `stream_name` for per-stream deduplication
  - `get_or_create_fingerprint_with_dedupe()` - added `stream_name` param
  - `check_near_duplicate_by_simhash()` - added `stream_name` param
- **`src/argus/db/models.py`**: Added `stream_name` field to `NewsFingerprintRow` and `NewsItemRow`
- **`src/argus/dedupe/near_duplicate.py`**: Added `stream_name` to `check_near_duplicate()` and `find_near_duplicates()`
- **`src/argus/ingestion/rss_worker.py`**: Pass `stream_name` from config to repository functions
- **`src/argus/config.py`**: Changed default stream name from `us_close_basic` to `us_markets`
- **`src/argus/facts_bundle/builder.py`**: Changed default stream name

### File Renames
- `rss/us_close_basic.txt` → `rss/us_markets.txt`

### Configuration Updates
- `config.yaml`: Updated `stream.name` and `rss.allowlist_files` to reference `us_markets`

### Test Updates
- Updated all test files to use `us_markets` instead of `us_close_basic`
- Updated test fixtures to include `stream_name` field in model row tuples

### Documentation Updates
- Updated `tasks/01_plan/spec.md` to reference `us_markets`

## Migration Instructions

**BREAKING CHANGE**: This migration requires running `argus db migrate` after code deployment.

1. Deploy new code
2. Run `argus db migrate` to apply migration 004
3. Verify with `argus db status`

## New Partition Naming Convention

After migration, partitions follow the pattern:
```
news_items_{stream}_{YYYY_MM_DD}
```

Example: `news_items_us_markets_2026_01_09`

## Per-Stream Deduplication

The same URL can now exist in multiple streams. Deduplication is scoped per-stream:
- URL hash checks filter by `stream_name`
- SimHash near-duplicate checks filter by `stream_name`
- Text hash checks filter by `stream_name`

## Verification Checklist
- [x] Migration file created
- [x] All code changes made
- [x] Tests pass (505 passed)
- [x] Type checking passes (pre-existing errors only)
- [x] Linting passes (pre-existing warnings only)
- [x] No references to `us_close_basic` remain in src/ or tests/

## Related Files
- Migration: `src/argus/db/migrations/004_multi_stream_schema.sql`
- Task: `tasks/03_archive/21-task.md` (archived)
