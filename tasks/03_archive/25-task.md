# Task 25: Friday Preview & Monday Newsletter — Weekly Statistics Infrastructure

## Goal

Build infrastructure to persist daily market snapshots and compute weekly statistics for:
1. **Friday Preview**: End-of-week market recap with week-over-week performance metrics
2. **Monday Newsletter**: Enhanced week-ahead outlook with historical context from the prior week

This task addresses the gap where market data is fetched fresh each run but never persisted, making week-over-week comparisons impossible.

## Current Status (2026-01-10)

- **Planning phase** — Task document created
- Current system fetches market data via yfinance at runtime but does NOT persist snapshots
- `weekend_wrap` runs Saturday 10:00 SGT (too late for Friday preview)
- `monday_preview` runs Sunday 18:10 NY but lacks weekly aggregated statistics
- All market data only exists in `facts_bundle_json` JSONB field (not queryable for trends)

## Background

### Current Market Data Flow

| Step | Location | Issue |
|------|----------|-------|
| Fetch indices | `src/argus/adapters/market_data.py` | Fresh fetch each run |
| Build snapshot | `MarketSnapshotBundle` dataclass | In-memory only |
| Store in bundle | `facts_bundle_json` in `runs` table | JSONB blob, not queryable |
| Calculate 5D return | `HistoricalMetrics` | Computed on-the-fly, not persisted |

### What's Missing for Weekly Statistics

| Metric | Currently Available | Needed For |
|--------|---------------------|------------|
| Daily index closes | No (only in JSON blobs) | Week-over-week % change |
| Weekly high/low | No | Range analysis |
| VIX weekly range | No | Volatility context |
| Yield weekly move | No | Rates narrative |
| News volume by day | Queryable but not aggregated | Theme trends |
| Sector performance | Not tracked | Rotation analysis |

### Investment Specialist Perspective

A senior macro analyst preparing a Friday preview would want:

**Weekly Performance Summary**:
- S&P 500 / Dow / Nasdaq: Week-over-week % change, weekly range
- Best/worst day of the week
- VIX: Weekly average, high, low (volatility regime)
- US 10Y: Weekly basis point move, direction
- DXY, Oil, Gold: Weekly % changes

**Theme Analysis**:
- Dominant news themes (by count and impact score)
- Key catalysts that moved markets
- Sector rotation signals

**Forward Look** (for Monday):
- Economic calendar highlights
- Earnings to watch
- Risk events

## Scope

### New Database Tables

#### `daily_market_snapshots`

Persists end-of-day market data for historical analysis.

```sql
CREATE TABLE daily_market_snapshots (
    id BIGSERIAL PRIMARY KEY,
    trading_date DATE NOT NULL,
    stream_name VARCHAR(100) NOT NULL DEFAULT 'us_markets',

    -- Core Indices
    sp500_close DECIMAL(10,2),
    sp500_change_pct DECIMAL(6,3),
    dow_close DECIMAL(10,2),
    dow_change_pct DECIMAL(6,3),
    nasdaq_close DECIMAL(10,2),
    nasdaq_change_pct DECIMAL(6,3),

    -- Cross-Assets
    vix_close DECIMAL(8,2),
    us10y_yield DECIMAL(5,3),
    dxy_close DECIMAL(8,3),
    wti_close DECIMAL(8,2),
    gold_close DECIMAL(10,2),

    -- Metadata
    fetched_at TIMESTAMPTZ NOT NULL,
    source VARCHAR(50) DEFAULT 'yfinance',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(trading_date, stream_name)
);

CREATE INDEX idx_daily_snapshots_date ON daily_market_snapshots(trading_date DESC);
CREATE INDEX idx_daily_snapshots_stream ON daily_market_snapshots(stream_name);
```

#### `weekly_market_summary` (Optional — Can Be Computed)

Pre-aggregated weekly statistics for fast retrieval.

```sql
CREATE TABLE weekly_market_summary (
    id BIGSERIAL PRIMARY KEY,
    week_ending DATE NOT NULL,  -- Friday's date
    stream_name VARCHAR(100) NOT NULL DEFAULT 'us_markets',

    -- Index Performance
    sp500_week_return_pct DECIMAL(6,3),
    sp500_week_high DECIMAL(10,2),
    sp500_week_low DECIMAL(10,2),
    dow_week_return_pct DECIMAL(6,3),
    nasdaq_week_return_pct DECIMAL(6,3),

    -- Volatility
    vix_week_avg DECIMAL(8,2),
    vix_week_high DECIMAL(8,2),
    vix_week_low DECIMAL(8,2),

    -- Rates & FX
    us10y_week_move_bps DECIMAL(6,1),
    dxy_week_change_pct DECIMAL(6,3),

    -- Commodities
    wti_week_change_pct DECIMAL(6,3),
    gold_week_change_pct DECIMAL(6,3),

    -- News Metrics
    total_news_items INT,
    high_impact_items INT,  -- impact_score >= 70
    dominant_themes TEXT[],  -- Top 3 topics by count

    -- Metadata
    trading_days INT,  -- 4-5 depending on holidays
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(week_ending, stream_name)
);
```

### New Files to Create

| File | Purpose |
|------|---------|
| `src/argus/db/migrations/005_daily_market_snapshots.sql` | Migration for new tables |
| `src/argus/adapters/market_snapshots.py` | Persist/retrieve daily snapshots, compute weekly stats |
| `src/argus/orchestrator/weekly_stats.py` | Weekly statistics calculator |
| `src/argus/generator/prompts_weekly.py` | Friday preview specific prompts (or extend existing) |
| `tests/test_market_snapshots.py` | Unit tests for snapshot persistence |
| `tests/test_weekly_stats.py` | Unit tests for weekly calculations |

### Files to Modify

| File | Changes |
|------|---------|
| `src/argus/adapters/market_data.py` | Add `persist_snapshot()` method after fetch |
| `src/argus/orchestrator/orchestrator.py` | Persist snapshot during `us_close` runs; add `friday_preview` mode |
| `src/argus/daemon/scheduler.py` | Add `friday_preview` job (Fri 22:00 NY or Sat 06:00 SGT) |
| `src/argus/facts_bundle/types.py` | Add `WeeklyStatsBundle` dataclass |
| `src/argus/facts_bundle/builder.py` | Include weekly stats in bundle for Friday/Monday modes |
| `src/argus/generator/prompts.py` | Add/modify prompts for weekly statistics focus |
| `src/argus/db/repository.py` | Add queries for snapshots and weekly aggregations |
| `config.yaml` | Add `friday_preview` schedule, enable snapshot persistence |

### Run Mode Changes

| Mode | Current | Proposed |
|------|---------|----------|
| `us_close` | Daily at 06:00 SGT | Add: persist `daily_market_snapshot` after run |
| `weekend_wrap` | Sat 10:00 SGT | Keep as-is OR rename to `friday_preview` |
| `friday_preview` | N/A | NEW: Fri 22:00 NY (Sat 11:00 SGT) with weekly stats focus |
| `monday_preview` | Sun 18:10 NY | Enhance: include prior week's statistics |

## Implementation Details

### 1. Daily Snapshot Persistence

After each `us_close` run, persist the market snapshot:

```python
# src/argus/adapters/market_snapshots.py

@dataclass
class DailySnapshot:
    trading_date: date
    sp500_close: Decimal
    sp500_change_pct: Decimal
    dow_close: Decimal
    dow_change_pct: Decimal
    nasdaq_close: Decimal
    nasdaq_change_pct: Decimal
    vix_close: Optional[Decimal] = None
    us10y_yield: Optional[Decimal] = None
    dxy_close: Optional[Decimal] = None
    wti_close: Optional[Decimal] = None
    gold_close: Optional[Decimal] = None

def persist_daily_snapshot(conn: Connection, snapshot: DailySnapshot, stream: str) -> None:
    """Upsert daily market snapshot."""
    # ON CONFLICT (trading_date, stream_name) DO UPDATE
    ...

def get_snapshots_for_week(conn: Connection, week_ending: date, stream: str) -> list[DailySnapshot]:
    """Retrieve Mon-Fri snapshots for a given week."""
    week_start = week_ending - timedelta(days=4)  # Monday
    ...
```

### 2. Weekly Statistics Calculator

```python
# src/argus/orchestrator/weekly_stats.py

@dataclass(frozen=True)
class WeeklyStats:
    week_ending: date
    trading_days: int

    # Index returns (Friday close vs prior Friday close)
    sp500_return_pct: Decimal
    dow_return_pct: Decimal
    nasdaq_return_pct: Decimal

    # Weekly ranges
    sp500_high: Decimal
    sp500_low: Decimal
    sp500_range_pct: Decimal  # (high - low) / low * 100

    # Volatility
    vix_avg: Decimal
    vix_high: Decimal
    vix_low: Decimal

    # Rates & FX
    us10y_move_bps: Decimal
    dxy_change_pct: Decimal

    # Commodities
    wti_change_pct: Decimal
    gold_change_pct: Decimal

    # Best/worst days
    best_day: tuple[date, Decimal]   # (date, sp500_change_pct)
    worst_day: tuple[date, Decimal]

def compute_weekly_stats(snapshots: list[DailySnapshot], prior_week_close: Optional[DailySnapshot]) -> WeeklyStats:
    """Calculate weekly aggregates from daily snapshots."""
    ...
```

### 3. WeeklyStatsBundle for Facts Bundle

```python
# src/argus/facts_bundle/types.py

@dataclass(frozen=True)
class WeeklyStatsBundle:
    week_ending: date
    trading_days: int

    # Performance
    sp500_return_pct: str      # e.g., "+1.23%"
    dow_return_pct: str
    nasdaq_return_pct: str

    # Volatility context
    vix_summary: str           # e.g., "VIX averaged 14.2 (range 12.8-15.9)"

    # Rates
    yield_summary: str         # e.g., "10Y yield +8bps to 4.52%"

    # Commodities
    commodity_summary: str     # e.g., "WTI +2.1%, Gold -0.5%"

    # Best/worst
    notable_days: str          # e.g., "Best: Wed +0.8%, Worst: Mon -0.4%"
```

### 4. Friday Preview Prompt

```python
SYSTEM_PROMPT_FRIDAY_PREVIEW = """
You are a senior investment analyst writing the weekly market recap for institutional clients.

Your report should cover:

1. **Weekly Performance Summary**
   - Start with the headline: how did equities perform this week?
   - Reference specific index returns (S&P 500, Dow, Nasdaq)
   - Note the VIX level and any volatility regime changes
   - Mention yield moves if significant (>10bps)

2. **Key Drivers**
   - What moved markets this week? Reference specific news items using [#CITEKEY]
   - Macro data releases and their impact
   - Policy signals (Fed, Treasury, etc.)
   - Geopolitical developments

3. **Sector/Theme Observations**
   - Which themes dominated? (Risk-on/off, growth vs value, etc.)
   - Notable sector moves if apparent from the news

4. **Week Ahead Setup**
   - Positioning going into next week
   - Key events on the calendar

CONSTRAINTS:
- Maximum {max_words} words
- Use ONLY facts provided in the bundle
- Reference news with EXACT citation keys [#A1B2C3D4]
- Professional, neutral tone
- Include specific numbers: percentages, basis points, dollar amounts

OUTPUT FORMAT:
{{
  "narrative": "2-4 paragraphs with citations",
  "weekly_scorecard": {{
    "sp500": "+X.X%",
    "dow": "+X.X%",
    "nasdaq": "+X.X%",
    "vix": "XX.X",
    "us10y": "X.XX%"
  }},
  "key_themes": ["theme1", "theme2", "theme3"],
  "watch_next_week": ["item1", "item2", "item3"]
}}
"""
```

### 5. Scheduler Configuration

```yaml
# config.yaml
schedule:
  daily_us_close_sgt: "06:00"      # Mon-Fri
  friday_preview_sgt: "11:00"      # Saturday (= Friday 22:00 NY)
  weekend_wrap_sgt: "10:00"        # Saturday (DEPRECATED or kept for different content)
  monday_preview_ny: "SUN 18:10"   # Sunday

market_snapshots:
  enabled: true
  persist_on_us_close: true
  retention_days: 365  # Keep 1 year of daily data
```

### 6. News Theme Aggregation

```python
# src/argus/orchestrator/weekly_stats.py

def get_weekly_news_themes(conn: Connection, week_start: date, week_end: date, stream: str) -> dict:
    """
    Aggregate news themes for the week.

    Returns:
        {
            "total_items": 45,
            "high_impact_items": 12,  # score >= 70
            "themes": [
                {"topic": "macro_catalyst", "count": 15, "avg_impact": 72.3},
                {"topic": "rates_credit", "count": 8, "avg_impact": 65.1},
                ...
            ],
            "top_sources": ["reuters.com", "bloomberg.com", "wsj.com"]
        }
    """
    ...
```

### 7. Integration with Monday Preview

Enhance `monday_preview` to include prior week context:

```python
# In facts_bundle/builder.py

def build_bundle(mode: RunMode, ...) -> FactsBundle:
    ...

    if mode in (RunMode.FRIDAY_PREVIEW, RunMode.MONDAY_PREVIEW):
        # Include weekly stats from prior week
        weekly_stats = compute_weekly_stats_for_bundle(conn, stream_name)
        bundle = bundle._replace(weekly_stats=weekly_stats)

    return bundle
```

## Acceptance Criteria

### Functional

| ID | Criterion | Verification |
|----|-----------|--------------|
| AC-1 | Daily snapshots persisted after each `us_close` run | Query `daily_market_snapshots` table after run |
| AC-2 | Weekly stats computed correctly | Unit test: 5 daily snapshots → correct weekly return |
| AC-3 | Friday preview includes week-over-week metrics | Generated message contains "Week: S&P 500 +X.X%" |
| AC-4 | Monday preview references prior week's performance | Generated message contains "Last week..." context |
| AC-5 | Holiday handling correct (4-day weeks) | Unit test: Thanksgiving week computes correctly |
| AC-6 | News theme aggregation by week | Query returns topic breakdown |

### Data Quality

| ID | Criterion | Verification |
|----|-----------|--------------|
| DQ-1 | Snapshots match yfinance data | Spot-check 5 random days against Yahoo Finance |
| DQ-2 | Weekly returns match manual calculation | Calculate S&P 500 week return manually, compare |
| DQ-3 | No duplicate snapshots per day | Unique constraint enforced |
| DQ-4 | Missing data handled gracefully | If VIX fetch fails, snapshot still persists with NULL |

### Performance

| ID | Criterion | Verification |
|----|-----------|--------------|
| PC-1 | Snapshot persistence < 100ms | Benchmark test |
| PC-2 | Weekly stats computation < 500ms | Benchmark test |
| PC-3 | 1 year of snapshots < 5MB storage | ~252 trading days × 15 columns |

### Quality Gates

- [ ] Migration applies cleanly
- [ ] All existing tests pass
- [ ] New unit tests for snapshot persistence
- [ ] New unit tests for weekly calculations
- [ ] `argus run friday-preview --dry-run` executes successfully
- [ ] Type checking passes (`mypy`)
- [ ] Linting passes (`ruff`)

## Out of Scope

- Sector ETF tracking (SPY, XLF, XLK, etc.) — future enhancement
- Intraday data (only daily close)
- International markets (only US for now)
- Backfilling historical snapshots (start fresh)
- Custom weekly report templates for different clients

## Risks / Notes

### Data Availability
- yfinance occasionally has delayed or missing data
- Need retry logic with exponential backoff
- Consider fallback to Alpha Vantage or Polygon if yfinance unreliable

### Holiday Handling
- US market holidays reduce trading days (4-day weeks)
- Half-days (day after Thanksgiving) need special handling
- Use `pandas_market_calendars` for accurate trading day detection

### Timing Considerations
- Friday US close is ~16:00 ET (21:00 UTC, 05:00 SGT+1)
- Allow 30-60 min buffer for settlement/final prices
- `friday_preview` at 22:00 NY (11:00 SGT Sat) gives buffer

### Prior Week Reference
- First week after launch will have no prior week data
- Handle gracefully: "Prior week data not available"

## Dependencies

- Task 24 (TheNewsAPI Integration) — independent, can run in parallel
- Task 23 (Scoring v2) — independent, scoring used for "high impact" classification

## Estimated Effort

| Component | Estimate |
|-----------|----------|
| Migration SQL | 30 min |
| `market_snapshots.py` (persist/retrieve) | 1 hour |
| `weekly_stats.py` (calculations) | 1.5 hours |
| `FactsBundle` integration | 1 hour |
| Prompt updates | 1 hour |
| Orchestrator changes | 1 hour |
| Scheduler configuration | 30 min |
| Unit tests | 2 hours |
| Integration testing | 1 hour |
| Documentation | 30 min |

**Total: ~10 hours**

## User Decisions Needed

| Decision | Options | Recommendation |
|----------|---------|----------------|
| Friday preview timing | Fri 22:00 NY vs Sat morning | Fri 22:00 NY (same day as close) |
| Keep `weekend_wrap`? | Replace vs keep both | Keep both (see note below) |
| Weekly summary table | Pre-compute vs compute on-demand | Compute on-demand initially |
| Snapshot retention | 90 days vs 1 year vs indefinite | 1 year (useful for YoY context) |

### Note on `weekend_wrap` vs `friday_preview`

**Keep `weekend_wrap`** — it serves a different purpose:
- `friday_preview`: End-of-week statistics recap (backward-looking)
- `weekend_wrap`: Week-ahead setup and positioning (forward-looking)

**Current Gap**: The forward-looking component of `weekend_wrap` is limited because our current news feeds only capture **this week's data**. We lack reliable sources for:
- Next week's economic calendar events (beyond what's in ForexFactory)
- Upcoming earnings announcements with expected impact
- Scheduled policy events (Fed speeches, Treasury auctions)
- Geopolitical events calendar

This is a separate concern that may require:
1. Integrating a dedicated economic calendar API (Investing.com, TradingEconomics)
2. Earnings calendar integration (Earnings Whispers, Zacks)
3. Fed/central bank calendar scraping

For now, `weekend_wrap` will continue using the existing economic calendar from ForexFactory, but the forward-looking narrative may be thin until we add dedicated calendar sources.
