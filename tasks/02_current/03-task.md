# Task 03: Build RSS ingestion worker (metadata + snippets)

## Goal
Continuously ingest RSS items into `news_items` without blocking run executions.

## Dependencies
- Depends on Task 01
- Depends on Task 02

## References
- `tasks/01_plan/spec.md` ((7) News Content Strategy, (8) Architecture: Ingestion Workers, (16) Secrets & Configuration: config.yaml rss)
- `rss/us_close_basic.txt`

## Scope
- Read allowlist URLs from `rss/*.txt` files defined by `config.yaml`.
- Poll on a cadence (default 5-15 min; configured).
- Normalize RSS entries into `news_items` fields (source, title, url, timestamp, snippet).
- Apply exact dedupe (URL hash + title/snippet hash) on write.
- Persist enough metadata for later enrichment/scoring selection.

## Acceptance criteria
- Running the worker against a small allowlist inserts new items and ignores duplicates.
- Ingestion continues while a run is executing (no global locks / no stop-the-world lock).
