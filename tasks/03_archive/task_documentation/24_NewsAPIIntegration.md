# Task 24: NewsAPI Integration

## Overview

Integrated [TheNewsAPI.com](https://www.thenewsapi.com) as an alternative ingestion source to RSS feeds, with multi-key rotation, smart pagination, and budget enforcement.

## Implementation

### Files Created/Modified

| File | Purpose |
|------|---------|
| `src/argus/pipeline/providers/news_api_client.py` | API client with key rotation |
| `src/argus/pipeline/providers/ingestion_api_newsapi.py` | Ingestion provider |
| `src/argus/pipeline/providers/ingestion_api_common.py` | Shared utilities |
| `src/argus/config.py` | `NewsApiConfig` dataclass |
| `apis/newsapi_us_markets.txt` | Stream-specific config |
| `tests/test_ingestion_api_newsapi.py` | Unit tests |
| `docs/integrations/newsapi.md` | Integration documentation |

### Key Features

#### 1. Multi-Key Rotation
- Supports multiple API keys via `NEWS_API_KEYS` environment variable
- Round-robin or failover rotation strategies
- Automatic failover on 402 (usage limit) and 429 (rate limit) errors

#### 2. Smart Pagination
Stops fetching when any of these conditions are met:
1. **Duplicate Detection**: ALL articles on a page already exist (caught up)
2. **End of Results**: Fewer articles returned than requested
3. **Max New Limit**: `max_new_per_run` reached (prevents bootstrap over-fetch)
4. **Budget Threshold**: `usage_remaining` <= `min_remaining_budget`
5. **Safety Limit**: `max_pages_safety_limit` reached

#### 3. Budget Enforcement
Prevents exhausting monthly API quota in one run:
```txt
# apis/newsapi_us_markets.txt
min_remaining_budget=10
```

When threshold is reached:
```
WARNING: Budget threshold reached: 8 requests remaining, threshold is 10
```

#### 4. Domain Filtering
Required configuration to preserve API quota:
```txt
domains=reuters.com,bloomberg.com,wsj.com
```

### Configuration

**Environment Variables:**
```bash
NEWS_API_KEYS="key1,key2,key3"  # Comma-separated
```

**Stream Config (`apis/newsapi_us_markets.txt`):**
```txt
locale=us
language=en
categories=business,technology,finance,markets
timeout_seconds=10
rotation_strategy=round_robin
domains=bbc.co.uk,businessinsider.com,theatlantic.com
lookback_hours=24
articles_per_request=3
max_new_per_run=30
min_remaining_budget=10
```

**Enable in `config.yaml`:**
```yaml
providers:
  ingestion: api_newsapi  # Instead of "rss"
```

### Testing

```bash
# Run unit tests
python -m pytest tests/test_ingestion_api_newsapi.py -v

# E2E test (real API)
# 1. Set NEWS_API_KEYS in .env
# 2. Edit config.yaml: providers.ingestion: api_newsapi
python -m argus ingest
```

### Design Decisions

1. **Sliding Window Pagination**: Stops on first duplicate page, not individual duplicates. This handles the case where API returns overlapping results across pages.

2. **Budget > Pagination**: Budget check runs after each request, ensuring we don't make another request if we're at the threshold.

3. **Header String Conversion**: API returns usage headers as strings. Fixed by adding proper `int()` conversion with error handling in `NewsApiResponse` properties.

4. **Config File Pattern**: Follows the same `{type}/{stream}.txt` pattern as RSS feeds for consistency.

## Test Results

- 23 unit tests covering:
  - ISO datetime parsing
  - Article normalization
  - Duplicate detection
  - Budget enforcement (5 tests)
  - Pagination stop conditions
- E2E testing verified budget enforcement with real API

## Related Tasks

- Task 17: Modularity & Per-Stream Providers (provider registry pattern)
- Task 3: RSS Ingestion Worker (ingestion pattern)
