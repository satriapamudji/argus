# Task 05: Add enrichment service (content fetcher)

## Goal
Fetch additional article content only for shortlisted items, respecting licensing/storage constraints.

## Dependencies
- Depends on Task 02
- Depends on Task 03
- Depends on Task 04

## References
- `tasks/01_plan/spec.md` ((7) News Content Strategy, (16) Secrets & Configuration: config.yaml enrichment)

## Scope
- Select top `K_enrich` items from a run window for enrichment.
- Fetch and parse article content with retries/backoff and clear `content_status` states.
- Respect `allow_full_text_storage`:
  - If false: store only an allowed excerpt length and structured metadata; never store full text.
  - If true: store cleaned full text (still keep content hashes).
- Record `content_hash` for change detection/dedupe.

## Acceptance criteria
- Enrichment runs against a controlled set of URLs and writes statuses + hashes to DB.
- The system degrades gracefully (snippet-only) when enrichment fails or is disabled.
