# Task 17: Modularity (Per-Stream Providers, DB as Integration Bus)

## Goal
Refactor Argus so that each pipeline stage can be swapped **per stream** via configuration, while keeping **Postgres as the primary integration bus**.

Stages in scope (priority order):
1) Ingestion  
2) Scoring  
3) Enrichment  
4) Publisher  

Later (out of scope for this task unless explicitly extended):
- Facts bundle selection/builder
- Generator / Validator (must explicitly integrate with Task 16 changes)

## Context: Task 16 is Complete (CITE_KEY Citations + Filtered Sources)
Task 16 (**Reliable Citations + Filtered Sources**) is done and archived. The system now relies on **stable `CITE_KEY` citations** and post-processing/renumbering so the `Sources` section shows **only cited sources**.

Implications for Task 17:
- Treat the Task 16 generator/renderer/validator behavior as the **baseline contract**.
- Do not reintroduce brittle ordinal `[n]` mapping.
- Modularity work should keep generator concerns out-of-scope, but must not break the Task 16 citation pipeline.

## Target Architecture
### Core principle: DB-backed stages + per-stream provider selection
Each stage is a provider implementation that:
- reads required inputs from DB
- writes outputs back to DB
- logs and returns lightweight stats

The orchestrator becomes a thin coordinator that calls providers resolved from config.

## Configuration Changes (Per Stream)
Extend `StreamConfig` in `src/argus/config.py` to include provider selectors.

### Provider selector shape (nested)
Selections live under a single `stream.providers` object.

Example `config.yaml`:
```yaml
stream:
  name: us_close_basic
  enabled: true

  providers:
    ingestion: rss
    scoring: heuristic_v1
    enrichment: fetch_extract
    publisher: telegram

  # Provider-specific configs remain in their existing blocks.
  # RSS ingestion uses EXACTLY ONE allowlist file per stream.
  rss:
    allowlist_files:
      - "rss/us_close_basic.txt"
    poll_interval_minutes: 10
```

Defaults (preserve current behavior):
- providers.ingestion = `rss`
- providers.scoring = `heuristic_v1`
- providers.enrichment = `fetch_extract`
- providers.publisher = `telegram`

Validation rule (ingestion):
- If `providers.ingestion == "rss"`, require `stream.rss.allowlist_files` to contain **exactly 1** file path.

## New Code: Pipeline Provider Interfaces
Create `src/argus/pipeline/` with:

### `src/argus/pipeline/interfaces.py`
Define thin DB-backed protocols (Python `Protocol`) for each stage:

- `IngestionProvider.run(*, config: ArgusConfig, conn) -> IngestionStats`
- `ScoringProvider.run(*, config: ArgusConfig, conn, window_hours: int, dry_run: bool) -> ScoringStats`
- `EnrichmentProvider.run(*, config: ArgusConfig, conn, window_hours: int) -> EnrichmentStats`
- `PublisherProvider.publish(*, config: ArgusConfig, conn, message_id: int, dry_run: bool, silent: bool) -> PublishResult`

Notes:
- “Stats” should reuse existing stats where possible (`IngestionStats`, `ScoringStats`, `EnrichmentStats`, `PublishResult`).
- Keep interfaces narrowly aligned to how Argus already runs.

### `src/argus/pipeline/registry.py`
- `get_ingestion_provider(stream_config) -> IngestionProvider`
- `get_scoring_provider(stream_config) -> ScoringProvider`
- `get_enrichment_provider(stream_config) -> EnrichmentProvider`
- `get_publisher_provider(stream_config) -> PublisherProvider`

Registry chooses provider by `stream.providers.<stage>`.

## Provider Implementations (Adapters Around Existing Code)
Create `src/argus/pipeline/providers/`:

### Ingestion (Priority #1)
- `RSSIngestionProvider` wraps existing `argus.ingestion.RSSWorker` / `run_ingestion(config)`

Acceptance: Selecting `rss` runs exactly the same ingestion behavior as today.

Optional “proof of modularity” ingestion provider (minimal + useful):
- `FixtureIngestionProvider` reads from a local fixture file and inserts into DB (handy for offline testing)
  - Only if low effort; otherwise defer.

### Scoring (Priority #2)
- `HeuristicScoringProvider` wraps existing `ScoringWorker`
- Keep `llm_triage_enabled` as an internal scoring config detail (not a provider yet)

### Enrichment (Priority #3)
- `FetchExtractEnrichmentProvider` wraps existing `EnrichmentWorker`
- Extractor registry remains unchanged (already modular internally)

### Publisher (Priority #4)
- `TelegramPublisherProvider` wraps existing `run_publish(...)` / `TelegramPublisher`
- Add `NullPublisherProvider` as an alternate provider to validate swapping end-to-end with minimal risk

#### Publisher DB semantics (NullPublisherProvider)
`NullPublisherProvider` is a **successful no-op** publisher. When selected:
- Set `messages.publish_status = "skipped"`
- Leave `messages.telegram_message_id = NULL`
- Leave `messages.published_at = NULL`
- Log that publishing was intentionally skipped due to provider=`null`
- Treat `publish_status="skipped"` as a **successful terminal state** for the run (not an error)
- Orchestrator continues normally and marks the run `completed`

## Orchestrator Refactor (Single Integration Point)
Modify `src/argus/orchestrator/orchestrator.py`:
- Replace direct imports/instantiations like `ScoringWorker(...)` and `TelegramPublisher(...)`
- Instead resolve providers via registry and call provider methods.

Example (conceptual):
```python
providers = resolve_providers(config.stream)
providers.ingestion.run(config=config, conn=conn)
providers.scoring.run(config=config, conn=conn, window_hours=..., dry_run=...)
...
providers.publisher.publish(config=config, conn=conn, message_id=..., dry_run=..., silent=...)
```

Keep current CLI flags (`--skip-scoring`, `--skip-enrichment`, `--skip-publish`, `--include-ingest`) working.

## Implementation Sequence (to minimize risk)
### Phase 0: Preconditions
- Task 16 is complete; ensure Task 17 does not regress `CITE_KEY` citation extraction, renumbering, or source filtering behavior.
- Avoid coupling provider interfaces to any legacy numeric `[n]` citation assumptions.

### Phase 1: Ingestion modularity
1. Add config: `stream.providers.ingestion`
2. Add interface + registry resolution for ingestion
3. Implement `RSSIngestionProvider`
4. Update orchestrator ingestion step to use provider
5. Tests: registry + orchestrator calls ingestion provider when enabled

### Phase 2: Scoring modularity
1. Add config: `stream.providers.scoring`
2. Interface + provider adapter `HeuristicScoringProvider`
3. Update orchestrator scoring step
4. Tests: scoring provider selection and invocation

### Phase 3: Enrichment modularity
1. Add config: `stream.providers.enrichment`
2. Adapter `FetchExtractEnrichmentProvider`
3. Update orchestrator enrichment step
4. Tests: enrichment provider selection and invocation

### Phase 4: Publisher modularity
1. Add config: `stream.providers.publisher`
2. Adapter `TelegramPublisherProvider`
3. Add `NullPublisherProvider`
4. Update orchestrator publish step to use provider
5. Tests: switch provider to null and ensure no Telegram calls, DB status updated as expected

## Testing Plan
Add new tests (names flexible):
- `tests/test_pipeline_registry.py`
  - asserts default providers when provider keys absent
  - asserts correct provider class when provider string set
- `tests/test_orchestrator_providers.py`
  - uses stub providers to confirm orchestrator calls stages in correct order given flags
- Publisher-specific test:
  - with `publisher.provider: null`, ensure publish step does not error and updates message publish_status appropriately

Run existing suite:
- `pytest`

## Acceptance Criteria
- Provider selection works **per stream** via `config.yaml`
- Orchestrator no longer directly depends on specific implementations for:
  - ingestion (RSSWorker)
  - scoring (ScoringWorker)
  - enrichment (EnrichmentWorker)
  - publishing (TelegramPublisher/run_publish)
- Default configuration continues existing behavior unchanged.
- `NullPublisherProvider` demonstrates swapping publisher without code changes.
- All existing tests pass, including Task 16 tests (once merged).

## Open Questions (need decision before implementation)
1) Provider naming convention:
   - Use short keys under `stream.providers.*`.
   - Initial provider keys (v1):
     - `providers.ingestion`: `rss`
     - `providers.scoring`: `heuristic_v1`
     - `providers.enrichment`: `fetch_extract`
     - `providers.publisher`: `telegram` | `null`

2) Scoring provider evolution:
   - `heuristic_v1` is the baseline.
   - Future provider swaps should follow the same pattern (e.g., `heuristic_v2`) without changing orchestrator code.

3) Ingestion allowlist constraint:
   - For `providers.ingestion == "rss"`, enforce exactly one `stream.rss.allowlist_files` entry per stream.

(If any of the above should differ, decide before implementing provider registry + orchestrator wiring.)
