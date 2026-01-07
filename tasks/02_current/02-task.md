# Task 02: Design Postgres schema + migrations

## Goal
Implement the Postgres data model and migrations needed for ingestion, scoring, runs, and publishing.

## Dependencies
- Depends on Task 01

## References
- `tasks/01_plan/spec.md` ((8) Architecture, (9) Database & Retention Strategy)

## Scope
- Tables (minimum): `news_items`, `news_scores`, `news_fingerprints`, `runs`, `messages` (+ optional `news_content` if storing excerpts/full text).
- Partition `news_items` by day on `ingested_at` and add a retention mechanism (drop old partitions).
- Indexing/constraints for dedupe:
  - Unique `hash_url` (sha256 of normalized URL)
  - `hash_text` for title+snippet
  - Storage for similarity signature (SimHash) and/or `pg_trgm` support
- Store run artifacts: facts bundle JSON, generated message, validation status, publish status, timings, and `monday_preview` risk breakdown (`risk_score`, `calendar_score`, `market_score`, `headline_score`).

## Acceptance criteria
- Migrations apply cleanly to an empty database.
- A minimal local script/command can insert a `news_item` and record a `run` + `message` row.
