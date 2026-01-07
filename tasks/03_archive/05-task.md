# Task 05: Add enrichment service (content fetcher)

## Status: ✅ COMPLETED

## Goal
Fetch additional article content only for shortlisted items, respecting licensing/storage constraints.

## Implementation Summary

### Files Created
- `src/argus/enrichment/__init__.py` - Module exports
- `src/argus/enrichment/types.py` - `FetchResult`, `EnrichmentResult`, `EnrichmentCandidate` dataclasses
- `src/argus/enrichment/fetcher.py` - `AsyncContentFetcher` with httpx, semaphore (2 concurrent), per-domain rate limiting (1 req/sec)
- `src/argus/enrichment/extractor.py` - HTML to clean text extraction using lxml
- `src/argus/enrichment/worker.py` - `EnrichmentWorker` class with `run()` method returning `EnrichmentStats`
- `tests/test_enrichment.py` - 32 tests covering types, extractor, fetcher

### Files Modified
- `pyproject.toml` - Added `httpx>=0.27` dependency
- `src/argus/db/repository.py` - Added `get_news_items_for_enrichment()`, `has_news_content()`, `insert_news_content()` functions
- `src/argus/cli.py` - Added `argus enrich --window-hours --dry-run` command

### Key Design Decisions
1. **Selection by impact_score** - Enrichment runs AFTER scoring. Items are selected by joining `news_items` + `news_scores`, ordered by `impact_score DESC`, excluding items already in `news_content`
2. **Async HTTP with httpx** - Better async performance. Uses semaphore (max 2 concurrent) + per-domain rate limiting (1 req/sec)
3. **Storage constraint** - Respects `allow_full_text_storage` config flag:
   - `false` → store truncated excerpt (`snippet_chars`, default 1200)
   - `true` → store full cleaned text
4. **Graceful degradation** - If no scored items exist, enrichment returns empty stats (no crash)
5. **Content hashing** - SHA256 hash stored with content for change detection/dedupe

### CLI Usage
```bash
# Show candidates without fetching
argus enrich --window-hours 24 --dry-run

# Run enrichment
argus enrich --window-hours 24
```

### Configuration
Uses existing `EnrichmentConfig` from `config.py`:
```yaml
stream:
  enrichment:
    enabled: true
    max_enrich_per_run: 25
    allow_full_text_storage: false
    snippet_chars: 1200
```

### Data Flow
```
Ingest (headlines, ~100+ items)
    ↓
Score (heuristics on title/snippet)
    ↓
Enrich (top K by impact_score, fetch full content)  ← THIS TASK
    ↓
LLM Triage (using enriched content)
```

## Acceptance Criteria Met
- ✅ Enrichment runs against a controlled set of URLs
- ✅ Writes statuses + hashes to DB (`news_content` table)
- ✅ Degrades gracefully when enrichment fails (stores failed status)
- ✅ Respects `allow_full_text_storage` config
- ✅ Records `content_hash` for change detection/dedupe

## Test Results
- 32 tests in `tests/test_enrichment.py` - all passing
- 184 total tests passing across entire project
- mypy: no issues
- ruff: all checks passed

## Completion Date
2026-01-07
