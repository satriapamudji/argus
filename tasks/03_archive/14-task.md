# Task 14: Source-Specific Content Extractors

## Goal
Create source-specific HTML extractors for CNBC and Nasdaq articles to improve content extraction quality, especially for:
- Removing mid-article RelatedContent (CNBC loses ~45% content without this)
- Filtering inline ads (Nasdaq)
- Extracting accurate author and publication date metadata

## Dependencies
- Depends on Task 08 (Enrichment Worker)

## References
- `tasks/01_plan/spec.md` (Content Enrichment)
- `docs/rss_feed_research_report.md` (RSS feed research)

## Scope

### RSS Feed Configuration
- Populate `rss/us_close_basic.txt` with 5 working feeds:
  - CNBC Top News: `https://www.cnbc.com/id/100003114/device/rss/rss.html`
  - CNBC World: `https://www.cnbc.com/id/100727362/device/rss/rss.html`
  - Nasdaq Markets: `https://www.nasdaq.com/feed/rssoutbound?category=Markets`
  - Nasdaq Earnings: `https://www.nasdaq.com/feed/rssoutbound?category=Earnings`
  - Nasdaq Commodities: `https://www.nasdaq.com/feed/rssoutbound?category=Commodities`

### Extractor Module
Created `src/argus/enrichment/extractors/` with:

1. **`base.py`** - Base classes
   - `ExtractedArticle` dataclass: content, author, published_at
   - `BaseExtractor` ABC: can_handle(), extract()

2. **`generic.py`** - Fallback extractor
   - Wraps existing lxml extraction logic from `extractor.py`
   - Handles any URL as fallback

3. **`cnbc.py`** - CNBC-specific extractor
   - Date: `time[data-testid="published-timestamp"]` (ISO 8601)
   - Author: `a.Author-authorName`
   - Content: `div.ArticleBody-articleBody`
   - Key fix: Removes `RelatedContent-relatedContent` embedded mid-article

4. **`nasdaq.py`** - Nasdaq-specific extractor
   - Date: `p.jupiter22-c-author-byline__timestamp` ("January 06, 2026 — 01:50 pm EST")
   - Author: `span.jupiter22-c-author-byline__author-no-link`
   - Content: `section.jupiter22-c-article-body`
   - Filters: `.ads__inline`, `.body__disclaimer`

5. **`__init__.py`** - Registry
   - `get_extractor(url)` returns appropriate extractor

### Worker Integration
Updated `src/argus/enrichment/worker.py`:
- Uses `get_extractor(url)` instead of `extract_article_text()`
- Added `_update_news_item_metadata()` to update `news_items.author` and `news_items.published_at` with page-extracted values
- Design decision: Always overwrite (Option B) when page extraction provides data

### Deprecation
Added deprecation notice to `src/argus/enrichment/extractor.py`:
- Points to new `argus.enrichment.extractors` module
- `truncate_to_excerpt()` still used by worker

## Files Created/Modified

| File | Action |
|------|--------|
| `src/argus/enrichment/extractors/__init__.py` | Created |
| `src/argus/enrichment/extractors/base.py` | Created |
| `src/argus/enrichment/extractors/generic.py` | Created |
| `src/argus/enrichment/extractors/cnbc.py` | Created |
| `src/argus/enrichment/extractors/nasdaq.py` | Created |
| `src/argus/enrichment/worker.py` | Modified |
| `src/argus/enrichment/extractor.py` | Modified (deprecation notice) |
| `rss/us_close_basic.txt` | Populated with 5 feeds |
| `tests/enrichment/__init__.py` | Created |
| `tests/enrichment/test_extractors.py` | Created (26 tests) |

## Acceptance Criteria
- [x] `get_extractor()` returns correct extractor for CNBC, Nasdaq, and unknown URLs
- [x] CNBC extractor removes RelatedContent mid-article sections
- [x] Nasdaq extractor filters ads and disclaimer
- [x] Date parsing handles various formats (AM/PM, noon, midnight)
- [x] Author extraction works for both sources
- [x] Worker updates `news_items` metadata when extractor provides values
- [x] All 26 tests pass
- [x] `rss/us_close_basic.txt` contains 5 working feeds

## Testing
```bash
# Run extractor tests
pytest tests/enrichment/test_extractors.py -v

# All 26 tests pass in 0.14s
```

## Design Decisions

1. **Extractor Registry Pattern**: First-match wins, GenericExtractor always last as fallback.

2. **Metadata Update Strategy (Option B)**: Always overwrite `news_items.author` and `published_at` when page extraction provides values. Rationale: Page-extracted data is more accurate than RSS feed data which may be missing or inconsistent.

3. **No Motley Fool**: Excluded despite initial consideration - focusing on working CNBC and Nasdaq feeds that we verified.

4. **Partitioned Table Optimization**: `_update_news_item_metadata()` uses both `id` and `ingested_at` in WHERE clause for partition pruning.
