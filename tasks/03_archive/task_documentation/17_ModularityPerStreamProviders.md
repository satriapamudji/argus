# Task 17: Modularity (Per-Stream Providers, DB as Integration Bus)

## Summary
Implemented a provider registry and thin provider interfaces so the orchestrator can swap ingestion/scoring/enrichment/publishing implementations **per stream** via `stream.providers.*`, while keeping Postgres as the integration bus. Default behavior remains the same as before.

A `null` publisher provider was added as a safe proving-ground: it performs a successful no-op publish and marks the message `publish_status="skipped"`.

## What Was Before
- The orchestrator directly instantiated/called concrete implementations (e.g. RSSWorker, ScoringWorker, EnrichmentWorker, Telegram publisher).
- Swapping implementations required orchestrator code changes.

## What Changed

### 1) Provider selectors added to config model (`src/argus/config.py`)
- Added `StreamProvidersConfig` and embedded it under `StreamConfig.providers`.
- Provider selection keys live under `stream.providers`:

```yaml
stream:
  providers:
    ingestion: rss
    scoring: heuristic_v1
    enrichment: fetch_extract
    publisher: telegram  # or: null
```

Defaults (preserve current behavior):
- ingestion: `rss`
- scoring: `heuristic_v1`
- enrichment: `fetch_extract`
- publisher: `telegram`

**Note on RSS allowlist validation**: the constraint “RSS ingestion requires exactly 1 allowlist file” is enforced at **runtime** in the RSS ingestion provider (instead of config load), so that `ArgusConfig.load()` remains usable even when ingestion is not exercised (and to avoid breaking existing config-loading tests).

### 2) Pipeline interfaces + provider registry (`src/argus/pipeline/`)
- Added `src/argus/pipeline/interfaces.py` with thin stage protocols.
- Added `src/argus/pipeline/registry.py` to resolve concrete providers from `stream.providers.*`.
- Added provider adapters under `src/argus/pipeline/providers/`:
  - `RSSIngestionProvider`
  - `HeuristicV1ScoringProvider`
  - `FetchExtractEnrichmentProvider`
  - `TelegramPublisherProvider`
  - `NullPublisherProvider`

### 3) Orchestrator now calls providers (`src/argus/orchestrator/orchestrator.py`)
- Refactored orchestrator to resolve providers via the registry and call the stage interface.
- Preserved existing CLI flags behavior (`--skip-*`, `--include-ingest`, etc.) while changing the “how” (providers) not the “what” (behavior).

### 4) Null publisher semantics (DB contract)
- `NullPublisherProvider` is a successful no-op publisher:
  - sets `messages.publish_status = "skipped"`
  - leaves `telegram_message_id` and `published_at` unset
  - returns `PublishResult(success=True, ...)`

This matches the schema constraint allowing `publish_status IN ('pending','published','failed','skipped')`.

## End-to-End / Regression Checks
- `python -m argus smoke` → PASSED
- `python -m argus run --stream us_close_basic --mode us_close --dry-run` → completed successfully (prints config + feed list)

## Test Results
- `pytest -q` → 494 passed, 5 skipped

## Files Created/Modified

### Created
- `src/argus/pipeline/interfaces.py`
- `src/argus/pipeline/registry.py`
- `src/argus/pipeline/providers/ingestion_rss.py`
- `src/argus/pipeline/providers/scoring_heuristic_v1.py`
- `src/argus/pipeline/providers/enrichment_fetch_extract.py`
- `src/argus/pipeline/providers/publisher_telegram.py`
- `src/argus/pipeline/providers/publisher_null.py`
- `tests/test_pipeline_registry.py`
- `tests/test_pipeline_null_publisher.py`
- `tests/test_pipeline_rss_provider_validation.py`
- `tests/test_config_providers.py`

### Modified
- `src/argus/config.py`
- `src/argus/orchestrator/orchestrator.py`

### Archived
- `tasks/03_archive/17-modularity.md` (moved from `tasks/02_current/17-modularity.md`)

## Notes / Follow-ups
- If we want stricter validation earlier, we can add a CLI-level preflight check for provider-specific requirements (without making `ArgusConfig.load()` fail).
- The `null` publisher can be used for safe end-to-end testing without Telegram credentials.
