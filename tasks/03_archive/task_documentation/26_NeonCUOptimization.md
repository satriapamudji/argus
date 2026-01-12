# Task 26: Neon CU Optimization - Reduce Database Compute Usage

## Overview

Goal: reduce Neon CU usage by cutting ingestion frequency, batching DB work, and removing heavy per-entry overhead.

**Date Completed**: 2026-01-12  
**Status**: Completed (type-check, lint, full test suite)

## Before

- Ingestion ran every 10 minutes; health ping every 10 minutes.
- Per-entry ingestion executed multiple queries and commits.
- Fingerprints used SELECT-then-INSERT pattern.
- Simhash near-duplicate checked a 14-day window in Python.
- No connection pooling.
- Missing composite indexes for stream + hash_text, stream + first_seen_at, and last_seen_at.

## Changes

1. **Config tuning** (`config.yaml`)
   - `rss.poll_interval_minutes`: 10 -> 20
   - `daemon.health_ping_minutes`: 10 -> 30
   - `dedupe.simhash`: `window_days` 14 -> 3, `hamming_threshold` 4 -> 3

2. **Indexes** (`src/argus/db/migrations/006_cu_optimization_indexes.sql`)
   - Added indexes for `(stream_name, hash_text)`, `(stream_name, first_seen_at)`, and `last_seen_at`.

3. **Batch ingestion + UPSERTs** (`src/argus/db/repository.py`)
   - Added `get_existing_url_hashes`, `upsert_fingerprints_batch`, `insert_news_items_batch`.
   - Switched `get_or_create_fingerprint` to an UPSERT with `last_seen_at` update.

4. **RSS ingestion batching** (`src/argus/ingestion/rss_worker.py`)
   - Batch URL dedupe, fingerprint UPSERT, and news item insert.
   - Safe fallback to per-entry ingestion if batch fails.

5. **NewsAPI ingestion batching** (`src/argus/pipeline/providers/ingestion_api_common.py`,
   `src/argus/pipeline/providers/ingestion_api_newsapi.py`)
   - Batch per-page ingestion with fallback to per-article logic.

6. **Server-side SimHash check** (`src/argus/dedupe/near_duplicate.py`)
   - Uses `bit_count` when available; falls back to Python Hamming distance.

7. **Connection pooling** (`src/argus/db/connection.py`)
   - Added a pooled connection wrapper with env overrides:
     - `DB_POOL_ENABLED` (default: true)
     - `DB_POOL_MIN` (default: 1)
     - `DB_POOL_MAX` (default: 5)

## Reasoning

- Batch inserts collapse N+1 patterns into single round-trips and fewer commits.
- UPSERT removes duplicate SELECTs and consolidates fingerprint updates.
- Server-side Hamming reduces row transfer and Python CPU for near-dup checks.
- Connection pooling reduces per-operation connection setup cost.
- Config changes reduce scheduler load and unnecessary wake-ups.

## Verification

- `python -m mypy src`
- `python -m ruff check src`
- `python -m pytest` (required escalated permissions to allow temp/cache writes on Windows)

All checks passed after rerunning pytest with escalated permissions.
