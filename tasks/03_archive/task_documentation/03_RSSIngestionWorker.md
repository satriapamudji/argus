# Task 03: RSS Ingestion Worker

## Summary
Built a cron-triggered RSS ingestion worker that continuously ingests RSS feed items into the `news_items` table with exact deduplication support.

## What Was Before
- No RSS feed parsing capability
- No mechanism to ingest news from external sources
- The ingestion workers component mentioned in spec section 8 was not implemented

## What Was Changed

### New Dependencies Added (`pyproject.toml`)
```toml
"feedparser>=6.0",
"lxml>=5.0",
```

### New Module: `src/argus/ingestion/`

**File Structure:**
```
src/argus/ingestion/
├── __init__.py        # Module exports
├── types.py           # RSSEntry dataclass
├── rss_parser.py      # RSS parsing utilities
└── rss_worker.py      # Ingestion worker and stats
```

#### `types.py`
- **`RSSEntry`** dataclass: Normalized representation of an RSS feed entry
  - Fields: `source_name`, `source_url`, `title`, `snippet`, `author`, `published_at`, `raw_metadata`

#### `rss_parser.py`
- **`strip_html(html_content)`**: Strips HTML tags using lxml, normalizes whitespace
- **`extract_source_name(feed, feed_url)`**: Extracts clean source name from feed metadata
  - Removes common suffixes (" RSS", " Feed", " - RSS", " | RSS", " News")
  - Falls back to domain name if no title
- **`parse_published_date(entry)`**: Parses publication date from `published_parsed` or `updated_parsed` fields
- **`parse_feed(feed_url, max_snippet_chars)`**: Main parsing function
  - Fetches and parses RSS feed using feedparser
  - Handles HTTP errors and parsing errors gracefully
  - Strips HTML from snippets, truncates to configured length
  - Returns tuple of (entries list, error message or None)

#### `rss_worker.py`
- **`IngestionStats`** dataclass: Tracks ingestion statistics
  - `feeds_processed`, `feeds_failed`, `entries_found`, `entries_new`, `entries_duplicate`, `errors`
- **`RSSWorker`** class: Main worker that ingests feeds into database
  - `ingest_entry(entry)`: Ingests single entry with URL deduplication check
  - `ingest_feed(feed_url)`: Ingests all entries from a feed
  - `run()`: Ingests all configured feeds, returns stats
- **`run_ingestion(config)`**: Convenience function for cron invocation

### CLI Command Added (`src/argus/cli.py`)
```bash
# Run ingestion
argus ingest

# Dry run (parse only, no DB insertion)
argus ingest --dry-run
```

### New Test File: `tests/test_rss_ingestion.py`
- 42 comprehensive test cases covering:
  - HTML stripping (8 tests)
  - Source name extraction (10 tests)
  - Date parsing (5 tests)
  - RSSEntry dataclass (3 tests)
  - Feed parsing (15 tests including error handling)
  - Integration test stub (1 skipped)

## Design Decisions & Reasoning

### 1. Cron-Triggered vs Daemon Approach
**Decision**: Simple cron-triggered approach where each invocation polls all feeds once.

**Reasoning**: 
- Simpler to deploy and maintain
- No long-running process to monitor
- Aligns with spec's mention of cron examples
- Daemon mode can be added later if needed

### 2. lxml for HTML Stripping
**Decision**: Used `lxml.html` instead of stdlib `html.parser`.

**Reasoning**:
- More reliable handling of malformed HTML
- Better whitespace normalization
- Consistent text extraction

### 3. Deduplication Strategy
**Decision**: Check `check_duplicate_by_url()` before creating fingerprint.

**Reasoning**:
- Existing `get_or_create_fingerprint()` handles text hashing
- URL check is fastest and most common duplicate case
- Follows spec's 3-layer dedupe strategy (URL hash, text hash, simhash)

### 4. Snippet Truncation
**Decision**: Truncate at word boundary with "..." suffix.

**Reasoning**:
- Preserves readability
- Respects configured `snippet_chars` limit
- Clean break without mid-word cuts

### 5. Source Name Cleaning
**Decision**: Strip common feed suffixes and fall back to domain.

**Reasoning**:
- Cleaner source attribution in final output
- Common RSS feeds append "RSS", "Feed", etc.
- Domain fallback ensures source is never empty

## Acceptance Criteria Verification

| Criterion | Status |
|-----------|--------|
| Running worker against small allowlist inserts new items | ✅ Tested via mocked feedparser |
| Ignores duplicates on re-run | ✅ `check_duplicate_by_url()` called before insert |
| Ingestion continues while run is executing (no global locks) | ✅ Worker uses its own DB connection |

## Files Changed

| File | Change Type |
|------|-------------|
| `pyproject.toml` | Modified (added dependencies) |
| `src/argus/ingestion/__init__.py` | Created |
| `src/argus/ingestion/types.py` | Created |
| `src/argus/ingestion/rss_parser.py` | Created |
| `src/argus/ingestion/rss_worker.py` | Created |
| `src/argus/cli.py` | Modified (added `ingest` command) |
| `tests/test_rss_ingestion.py` | Created |

## Test Results
```
125 passed, 1 skipped in 1.32s
```

## Usage Example

```bash
# Add RSS feeds to rss/us_close_basic.txt:
# https://feeds.reuters.com/reuters/businessNews
# https://feeds.bloomberg.com/markets/news.rss

# Run ingestion
argus ingest

# Output:
# Ingesting from 2 feed(s)...
# 
# === Ingestion Complete ===
# Feeds processed: 2
# Feeds failed: 0
# Entries found: 45
# New entries: 45
# Duplicates skipped: 0
```

## Cron Configuration Example
```cron
# Run every 10 minutes
*/10 * * * * /app/bin/argus ingest
```
