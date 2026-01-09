# NewsAPI Integration

Integration with [TheNewsAPI.com](https://www.thenewsapi.com) for fetching real-time news articles.

## Configuration

### API Keys (Environment)

```bash
# Set in .env - comma-separated for key rotation
NEWS_API_KEYS="key1,key2,key3"
```

### Stream Config (apis/newsapi_{stream}.txt)

All configuration lives in the `apis/` directory, following the same pattern as RSS feeds:

```
apis/newsapi_us_markets.txt
```

**File format:** `key=value` (one per line)

```txt
# NewsAPI configuration for us_markets stream

# Core settings
locale=us
language=en
categories=business,technology,finance,markets
timeout_seconds=10

# Rotation strategy: round_robin or failover
rotation_strategy=round_robin

# Domain filtering (required - preserves API quota)
domains=reuters.com,bloomberg.com,wsj.com

# Ingestion settings
lookback_hours=24
articles_per_request=3
max_new_per_run=30

# Budget enforcement
min_remaining_budget=10
```

#### Available Settings

| Setting | Description | Default |
|---------|-------------|---------|
| `locale` | Country code for news | `us` |
| `language` | Language code | `en` |
| `categories` | Comma-separated category filter | (all) |
| `timeout_seconds` | HTTP timeout | `10` |
| `rotation_strategy` | `round_robin` or `failover` | `round_robin` |
| `domains` | Comma-separated domain filter (required) | (none) |
| `lookback_hours` | How far back to fetch articles | `1` |
| `articles_per_request` | Articles per API call | `3` |
| `max_new_per_run` | Max new articles per ingestion run | `50` |
| `max_pages_safety_limit` | Safety limit for pagination | `50` |
| `min_remaining_budget` | Stop when API quota drops to this | `10` |

## Ingestion Provider

To use NewsAPI for ingestion instead of RSS:

```yaml
# config.yaml
providers:
  ingestion: api_newsapi  # Instead of "rss"
```

### Pagination Logic

The ingestion provider uses smart pagination to minimize API usage:

1. **Sliding Window**: Fetches pages until ALL articles on a page are duplicates (caught up to previous ingestion)
2. **End of Results**: Stops when fewer articles than requested are returned
3. **Max New Limit**: Stops after `max_new_per_run` new articles (prevents over-fetching on bootstrap)
4. **Budget Enforcement**: Stops when `usage_remaining` drops to `min_remaining_budget`
5. **Safety Limit**: Hard stop at `max_pages_safety_limit` pages

### Budget Enforcement

Prevents burning through your entire monthly API quota in one run:

```txt
# apis/newsapi_us_markets.txt
min_remaining_budget=10
```

| Value | Behavior |
|-------|----------|
| `10` (default) | Stop when 10 requests remain |
| `0` | Disabled (not recommended) |
| `50` | Conservative - preserves 50 requests |

When the budget threshold is reached:
```
WARNING: Budget threshold reached: 8 requests remaining, threshold is 10
```

## Key Rotation Strategy

### Round-Robin (Default)
Requests are distributed evenly across all configured keys. When a key hits a limit (402/429), the client rotates to the next key and retries.

```python
# Keys: [key_a, key_b, key_c]
# Request 1 -> key_a
# Request 2 -> key_b
# Request 3 -> key_c
# Request 4 -> key_a (loops)
```

### Failover
Uses the primary key first. Only rotates to the next key when the primary fails with 402/429.

```python
# Keys: [key_a, key_b]
# Request 1 -> key_a
# If key_a fails -> key_b (and stays on key_b)
```

## Usage

```python
from argus.config import NewsApiConfig
from argus.pipeline.providers.news_api_client import NewsApiClient

config = NewsApiConfig(config_file="apis/newsapi_us_markets.txt")
client = NewsApiClient(config)

# Fetch headlines using config settings
response = client.get_headlines(limit=10)
for article in response.data:
    print(f"{article.title} - {article.source}")

# Override config settings
response = client.get_headlines(locale="gb", categories=["business"])

# Check usage
status = client.get_usage_status()
for s in status:
    print(f"Key {s['key_index']}: {s['remaining']}/{s['limit']} remaining")
```

## Response Structure

```python
@dataclass
class NewsArticle:
    uuid: str                    # Unique identifier
    title: str                   # Article headline
    description: Optional[str]   # Summary
    snippet: Optional[str]       # Short excerpt
    url: str                     # Link to article
    image_url: Optional[str]     # Featured image
    language: str                # e.g., "en"
    published_at: str            # ISO datetime
    source: str                  # Publisher name
    categories: list[str]        # e.g., ["business"]
    relevance_score: Optional[float]
    keywords: list[str]
```

## Error Handling

```python
from argus.pipeline.providers.news_api_client import (
    NewsApiClient,
    UsageLimitError,
    RateLimitError,
    NewsApiError,
)

try:
    response = client.get_headlines(locale="us")
except UsageLimitError as e:
    print(f"Key {e.key_index} exhausted: {e.remaining}/{e.limit} remaining")
    # Rotate to next key or alert
except RateLimitError as e:
    print(f"Rate limited. Retry after {e.retry_after} seconds")
    # Wait and retry
except NewsApiError as e:
    print(f"API error {e.status_code}: {e}")
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `get_headlines()` | `/news/headlines` | Breaking news headlines |
| `get_top()` | `/news/top` | Top curated stories |
| `get_all()` | `/news/all` | All news with filters |
| `get_by_uuid()` | `/news/uuid/{uuid}` | Single article |
| `get_similar()` | `/news/similar/{uuid}` | Related articles |
| `get_sources()` | `/news/sources` | Available sources |

## Categories

Available categories vary by plan. Common options:
- `business`
- `technology`
- `economy`
- `finance`
- `markets`
- `politics`
- `science`
- `health`
- `entertainment`
- `sports`

## Usage Tracking

The client tracks usage via HTTP headers:

- `X-UsageLimit-Limit`: Monthly quota for the key
- `X-UsageLimit-Remaining`: Requests left this month
- `X-RateLimit-Limit`: Rate limit window
- `X-RateLimit-Remaining`: Requests left in window

```python
response = client.get_headlines()
print(f"Limit: {response.usage_limit}")
print(f"Remaining: {response.usage_remaining}")
```

## Plan Limits (402 Error)

When you hit your plan's monthly limit:
- Status: `402 Payment Required`
- Header: `X-UsageLimit-Limit: 0`
- Action: Rotate to next key or wait for reset
