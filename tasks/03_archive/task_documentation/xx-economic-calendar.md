# Economic Calendar Feature

The economic calendar feature integrates ForexFactory's free JSON feed to populate the "Key Dates (UTC)" section in generated market update messages.

## Overview

High-impact economic events (like Non-Farm Payrolls, CPI, FOMC decisions) are automatically fetched from ForexFactory and stored in PostgreSQL. When generating a market update, upcoming events are included in the facts bundle for the LLM to reference.

## Configuration

Add to your `config.yaml`:

```yaml
stream:
  economic_calendar:
    enabled: true
    feed_url: "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    countries:
      - USD
    impact_filter:
      - High
    lookahead_days: 7
    stale_hours: 12
```

### Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `enabled` | `true` | Enable/disable the feature |
| `feed_url` | ForexFactory URL | JSON feed source |
| `countries` | `["USD"]` | Filter by country codes |
| `impact_filter` | `["High"]` | Filter by impact level (High, Medium, Low, Holiday) |
| `lookahead_days` | `7` | How many days ahead to include events |
| `stale_hours` | `12` | Auto-refresh if data is older than this |

## CLI Commands

### Refresh Calendar Data

Manually fetch latest events from ForexFactory:

```bash
argus calendar refresh
```

### Show Upcoming Events

Display upcoming events:

```bash
# Next 7 days (default)
argus calendar show

# Next 14 days
argus calendar show --days 14
```

### Check Status

View configuration and data freshness:

```bash
argus calendar status
```

## Cron Setup

For production, set up cron to refresh the calendar regularly:

```bash
# Refresh economic calendar every 6 hours
0 */6 * * * cd /path/to/argus && bin/argus calendar refresh >> /var/log/argus/calendar.log 2>&1
```

Or use the stale-hours feature for automatic refresh during bundle generation:
- If data is older than `stale_hours`, it refreshes automatically when building a bundle
- No separate cron needed, but adds latency to bundle generation

## Database Schema

The feature uses the `economic_calendar_events` table:

```sql
CREATE TABLE economic_calendar_events (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    country VARCHAR(10) NOT NULL,
    event_timestamp TIMESTAMPTZ NOT NULL,
    impact TEXT NOT NULL CHECK (impact IN ('High', 'Medium', 'Low', 'Holiday')),
    forecast TEXT,
    previous TEXT,
    actual TEXT,
    source TEXT NOT NULL DEFAULT 'forexfactory',
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(title, event_timestamp, source, country)
);
```

Apply the migration:

```bash
argus db migrate
```

## How It Works

1. **Fetch**: HTTP GET to ForexFactory JSON feed
2. **Parse**: Extract events, filter by country and impact
3. **Convert**: Timestamps converted to UTC
4. **Upsert**: Store in PostgreSQL with deduplication
5. **Query**: Bundle builder fetches upcoming events
6. **Display**: Events formatted as "Jan 8 14:30 UTC - Event Name"

## Output Format

In the generated message, events appear in the "Key Dates (UTC)" section:

```
📅 Key Dates (UTC)
Jan 8 14:30 UTC - Non-Farm Payrolls
Jan 10 19:00 UTC - FOMC Minutes
Jan 14 13:30 UTC - CPI m/m
```

## Troubleshooting

### No events showing

1. Check if the migration has been applied: `argus db status`
2. Refresh the calendar: `argus calendar refresh`
3. Verify configuration: `argus calendar status`

### Stale data warnings

Run `argus calendar refresh` or reduce `stale_hours` in config.

### HTTP errors during refresh

Check your network connectivity to `nfs.faireconomy.media`. The feed is publicly available without authentication.

## Data Source

ForexFactory provides a free JSON feed with economic calendar data:
- URL: `https://nfs.faireconomy.media/ff_calendar_thisweek.json`
- Updates: Weekly data, refreshed periodically
- No authentication required
- Rate limiting: Be respectful, don't hammer the endpoint
