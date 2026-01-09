# Task 24: TheNewsAPI Integration (`api_newsapi` Provider)

## Goal

Integrate TheNewsAPI.com as an alternative ingestion source alongside RSS, using the provider registry pattern. Create a reusable `ingestion_api_common` module for future API integrations.

## Current Status (2026-01-09)

- **Implementation complete** - All files created/modified, tests passing
- All 18 new tests pass
- All 528 existing tests still pass
- No type errors in modified files

## Background

The RSS ingestion provider is limited by feed availability and update frequency. TheNewsAPI provides programmatic access to news from tier-1 sources (Reuters, Bloomberg, WSJ) with better filtering capabilities.

### Existing Infrastructure

| Component | Location | Status |
|-----------|----------|--------|
| `NewsApiClient` | `src/argus/pipeline/providers/news_api_client.py` | EXISTS - has `get_all()`, `get_top()`, key rotation |
| `NewsApiConfig` | `src/argus/config.py` (lines 360-473) | EXISTS - reads from `apis/newsapi_{stream}.txt` |
| Config file | `apis/newsapi_us_markets.txt` | EXISTS - needs new settings |
| Provider registry | `src/argus/pipeline/registry.py` | EXISTS - only supports `"rss"` currently |

### User Decisions

| Decision | Choice |
|----------|--------|
| Provider key | `api_newsapi` |
| Ingestion mode | Exclusive (RSS OR API per stream, not both) |
| Endpoint | `/news/all` |
| Missing API keys | Fail fast with clear error |
| Domain filtering | Required (preserve quota) |
| Lookback window | 1 hour (`published_after`) |
| Pagination | Smart - stop on duplicate, max 3 pages |
| Articles per request | Configurable (default 3) |
| Domains | Tier-1 only: `reuters.com`, `bloomberg.com`, `wsj.com` |

## Scope

### New Files to Create

| File | Purpose |
|------|---------|
| `src/argus/pipeline/providers/ingestion_api_common.py` | Shared utilities: `NormalizedArticle`, `ingest_article()`, `parse_iso_datetime()` |
| `src/argus/pipeline/providers/ingestion_api_newsapi.py` | `NewsApiIngestionProvider` with smart pagination |
| `tests/test_ingestion_api_newsapi.py` | Unit tests for the provider |

### Files to Modify

| File | Changes |
|------|---------|
| `src/argus/config.py` | Extend `NewsApiConfig` with `domains`, `lookback_hours`, `max_pages`, `articles_per_request` |
| `apis/newsapi_us_markets.txt` | Add new settings |
| `src/argus/pipeline/registry.py` | Register `api_newsapi` provider |
| `src/argus/cli.py` | 1) Update `argus ingest` to use provider registry; 2) Add `argus newsapi sources` command |
| `tests/test_pipeline_registry.py` | Add test for `api_newsapi` selection |

## Implementation Details

### 1. NormalizedArticle (ingestion_api_common.py)

```python
@dataclass
class NormalizedArticle:
    """API-agnostic article representation for DB insertion."""
    url: str                          # Primary deduplication key
    title: str
    snippet: Optional[str]            # Description or summary
    source_name: str                  # Domain (e.g., "reuters.com")
    published_at: Optional[datetime]  # Parsed datetime
    author: Optional[str] = None      # API rarely provides this
    raw_metadata: dict = field(default_factory=dict)  # API-specific fields
```

### 2. Helper Functions (ingestion_api_common.py)

```python
def parse_iso_datetime(dt_string: Optional[str]) -> Optional[datetime]:
    """Parse ISO 8601 datetime string, return None on failure."""
    
def ingest_article(
    conn: Connection,
    article: NormalizedArticle,
    stream_name: str,
) -> bool:
    """
    Insert article into news_items if not duplicate.
    Returns True if inserted, False if duplicate.
    Uses existing: check_duplicate_by_url(), get_or_create_fingerprint(), insert_news_item()
    """
```

### 3. NewsApiIngestionProvider (ingestion_api_newsapi.py)

```python
class NewsApiIngestionProvider:
    """Ingestion provider for TheNewsAPI."""
    
    def __init__(self, stream_config: StreamConfig, app_config: AppConfig):
        self.config = app_config.get_newsapi_config(stream_config.name)
        self._validate_config()  # Fail fast if no API keys
    
    def run(self, conn: Connection) -> IngestionStats:
        """
        Fetch articles with smart pagination:
        1. Calculate published_after from lookback_hours
        2. For each page (1 to max_pages):
           - Fetch articles with domains filter
           - For each article:
             - Normalize → NormalizedArticle
             - ingest_article() → track new vs duplicate
           - If hit duplicate or returned < limit: stop pagination
        3. Return IngestionStats
        """
```

### 4. NewsArticle → NormalizedArticle Mapping

| NewsArticle field | NormalizedArticle field | Notes |
|-------------------|-------------------------|-------|
| `url` | `url` | Primary deduplication key |
| `source` | `source_name` | Domain string |
| `title` | `title` | |
| `description` OR `snippet` | `snippet` | Prefer description (longer) |
| `published_at` | `published_at` | Parse ISO string → datetime |
| `uuid`, `categories`, `keywords`, `image_url` | `raw_metadata` | JSON dict |
| N/A | `author` | API doesn't provide, set to None |

### 5. Config Extensions (config.py)

Add to `NewsApiConfig`:

```python
@property
def domains(self) -> list[str]:
    """Domains to filter articles by (e.g., ['reuters.com', 'bloomberg.com'])."""
    
@property
def lookback_hours(self) -> int:
    """Hours to look back for articles. Default: 1."""
    
@property
def max_pages(self) -> int:
    """Maximum pages to fetch. Default: 3."""
    
@property
def articles_per_request(self) -> int:
    """Articles per API request. Default: 3."""
```

### 6. Config File Update (apis/newsapi_us_markets.txt)

```
locale=us
language=en
categories=business,technology,finance,markets
timeout_seconds=10
rotation_strategy=round_robin
# New settings
domains=reuters.com,bloomberg.com,wsj.com
lookback_hours=1
max_pages=3
articles_per_request=3
```

### 7. Registry Update (registry.py)

```python
supported = {"rss", "api_newsapi"}

def get_ingestion_provider(stream: StreamConfig, config: AppConfig) -> IngestionProvider:
    key = stream.providers.ingestion
    if key == "rss":
        return RSSIngestionProvider(stream, config)
    elif key == "api_newsapi":
        from argus.pipeline.providers.ingestion_api_newsapi import NewsApiIngestionProvider
        return NewsApiIngestionProvider(stream, config)
    raise ValueError(f"Unknown ingestion provider: {key}")
```

### 8. CLI Updates (cli.py)

#### Update `argus ingest` to use provider registry:

```python
@cli.command()
@click.option("--stream", default="us_markets")
def ingest(stream: str):
    """Ingest news items using configured provider."""
    config = load_config()
    stream_config = config.get_stream(stream)
    provider = get_ingestion_provider(stream_config, config)
    
    with get_connection() as conn:
        stats = provider.run(conn)
    
    click.echo(f"Ingested {stats.new} new items, {stats.duplicates} duplicates")
```

#### Add `argus newsapi sources` command:

```python
@cli.group()
def newsapi():
    """TheNewsAPI utilities."""
    pass

@newsapi.command()
@click.option("--language", default="en")
@click.option("--locale", default="us")
@click.option("--categories", default=None, help="Comma-separated categories")
def sources(language: str, locale: str, categories: Optional[str]):
    """List available news sources from TheNewsAPI."""
    # Use NewsApiClient.get_sources() to fetch and display available domains
```

### 9. Smart Pagination Logic

```python
def run(self, conn: Connection) -> IngestionStats:
    client = NewsApiClient(self.config.api_keys, ...)
    published_after = datetime.utcnow() - timedelta(hours=self.config.lookback_hours)
    
    stats = IngestionStats()
    
    for page in range(1, self.config.max_pages + 1):
        response = client.get_all(
            language=self.config.language,
            domains=",".join(self.config.domains),
            published_after=published_after.isoformat(),
            limit=self.config.articles_per_request,
            page=page,
        )
        
        hit_duplicate = False
        for article in response.data:
            normalized = self._normalize(article)
            if ingest_article(conn, normalized, self.stream_name):
                stats.new += 1
            else:
                stats.duplicates += 1
                hit_duplicate = True
        
        # Stop conditions
        if hit_duplicate or response.returned < self.config.articles_per_request:
            break
    
    return stats
```

## Acceptance Criteria

### Functional

| ID | Criterion | Verification |
|----|-----------|--------------|
| AC-1 | `api_newsapi` provider registered and selectable | `get_ingestion_provider()` returns `NewsApiIngestionProvider` |
| AC-2 | Missing API keys fail fast with clear message | Unit test: `ValueError` raised with helpful message |
| AC-3 | Articles deduplicated by URL | Unit test: second ingest of same URL returns False |
| AC-4 | Smart pagination stops on duplicate | Unit test: verify page loop breaks early |
| AC-5 | `argus ingest` works with both RSS and API providers | Integration test |
| AC-6 | `argus newsapi sources` lists available domains | Manual verification |
| AC-7 | ISO datetime strings parsed correctly | Unit test: various formats |

### Quality Gates

- [ ] All existing ingestion tests pass
- [ ] New unit tests for provider and helpers
- [ ] Type checking passes (`mypy`)
- [ ] Linting passes (`ruff`)
- [ ] `argus ingest --stream us_markets` works with `api_newsapi` provider

## Out of Scope

- Combining RSS + API in same stream (exclusive mode only)
- Automatic domain discovery
- Rate limit backoff beyond existing client logic
- Historical backfill

## Risks / Notes

- TheNewsAPI free tier: 100 requests/day, 3 articles/request
- `published_at` from API is ISO string, needs parsing
- Domain filtering is essential to preserve quota
- `/news/all` does NOT support `locale` parameter - use `domains` filter instead

## Dependencies

- Task 23 (Scoring v2) - independent, can run in parallel

## Estimated Effort

| Component | Estimate |
|-----------|----------|
| `ingestion_api_common.py` | 30 min |
| `ingestion_api_newsapi.py` | 1 hour |
| Config extensions | 30 min |
| Registry + CLI updates | 30 min |
| Unit tests | 1 hour |
| Manual verification | 30 min |

**Total: ~4 hours**
