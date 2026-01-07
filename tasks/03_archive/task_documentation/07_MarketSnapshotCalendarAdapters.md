# Task 07: Market Snapshot + Calendar Data Adapters

## Summary
This task implemented market data and calendar adapters to provide the market and catalyst inputs required by the facts bundle. These adapters fetch US cash close snapshots and provide NYSE trading calendar information.

## What Was Added

### New Module Structure
```
src/argus/adapters/
├── __init__.py          # Module exports
├── market_data.py       # Market data provider using yfinance
└── calendar.py          # NYSE calendar adapter using exchange_calendars
```

### Market Data Adapter (`market_data.py`)

**Data Classes:**
- `IndexSnapshot` - Immutable snapshot of a single market index with:
  - name, symbol, level (price)
  - change_1d_pct (1-day percentage change)
  - change_1d_pts (1-day point change)
  - as_of timestamp

- `CrossAssetMetrics` - Optional cross-asset metrics:
  - VIX (level, change %)
  - US 10Y Treasury yield (yield, change bps)
  - DXY Dollar Index (level, change %)
  - WTI Crude Oil (level, change %)
  - Gold & Silver (level, change %)

- `MarketSnapshot` - Complete market snapshot containing:
  - trading_date
  - sp500, dow, nasdaq (IndexSnapshot)
  - cross_assets (optional CrossAssetMetrics)
  - fetched_at timestamp

**Provider Class:**
- `MarketDataProvider` - Fetches market data using yfinance
  - Lazy-loads yfinance module (optional dependency pattern)
  - Uses `fast_info` for efficient snapshots with history fallback
  - Graceful error handling for missing data
  - Optional cross-asset fetching via `include_cross_assets` flag

**Ticker Symbol Mappings:**
- S&P 500: `^GSPC`
- Dow Jones: `^DJI`
- Nasdaq: `^IXIC`
- VIX: `^VIX`
- US 10Y: `^TNX`
- DXY: `DX-Y.NYB`
- WTI: `CL=F`
- Gold: `GC=F`
- Silver: `SI=F`

### Calendar Adapter (`calendar.py`)

**Data Classes:**
- `CatalystType` - Enum for event types:
  - CENTRAL_BANK, ECONOMIC_DATA, EARNINGS, POLITICAL
  - AUCTION, HOLIDAY, HALF_DAY, OTHER

- `Catalyst` - Market catalyst event with UTC timezone labeling:
  - name, catalyst_type, timestamp_utc
  - Optional: description, impact_score, source
  - Auto-converts non-UTC timestamps to UTC
  - `format_for_display()` method for Key Dates section

- `TradingDayInfo` - Information about a specific trading day:
  - date, is_trading_day, is_holiday, is_half_day
  - holiday_name, close_time_utc

**Adapter Class:**
- `MarketCalendarAdapter` - NYSE trading calendar operations:
  - Lazy-loads exchange_calendars module
  - `is_trading_day(date)` - Check if date is a trading session
  - `is_holiday(date)` - Check if weekday is a market holiday
  - `is_early_close(date)` - Check for half-day/early close
  - `get_trading_day_info(date)` - Comprehensive trading day info
  - `get_previous_trading_day(date)` - Most recent trading day
  - `get_next_trading_day(date)` - Next trading day
  - `get_trading_days_in_range(start, end)` - All trading days in range
  - `get_next_n_trading_days(date, n)` - Next N trading days
  - `get_holidays_in_range(start, end)` - All holidays in range
  - `get_early_closes_in_range(start, end)` - All early close days

**Factory Function:**
- `create_catalyst()` - Creates Catalyst with proper UTC handling

### Dependencies Added to `pyproject.toml`
```toml
"yfinance>=0.2.40",
"exchange_calendars>=4.5",
"pandas>=2.0",
```

### Tests Added
- `tests/test_market_data.py` - 16 tests covering:
  - IndexSnapshot creation and immutability
  - CrossAssetMetrics with partial data
  - MarketSnapshot creation
  - Symbol mappings validation
  - MarketDataProvider initialization
  - yfinance lazy loading
  - Snapshot fetching (fast_info and history fallback)
  - Error handling for missing data

- `tests/test_calendar.py` - 22 tests covering:
  - CatalystType enum values
  - Catalyst UTC conversion and formatting
  - TradingDayInfo creation
  - MarketCalendarAdapter initialization
  - Calendar lazy loading
  - Trading day detection (weekday, weekend, holiday)
  - Previous/next trading day navigation
  - Trading days in range
  - Holiday detection

## Design Decisions

### Lazy Loading Pattern
Both adapters use lazy loading for their respective libraries (yfinance, exchange_calendars). This:
- Reduces startup time when adapters aren't used
- Provides clear error messages if dependencies are missing
- Allows the core package to work without optional dependencies

### UTC Timezone Enforcement
The `Catalyst` class enforces UTC timezone for all timestamps:
- Naive datetimes are assumed to be UTC and converted
- Non-UTC aware datetimes are converted to UTC
- This ensures consistent timezone handling for the `*Key Dates (UTC)*` section

### Immutable Data Classes
Both `IndexSnapshot` and `Catalyst` use `@dataclass(frozen=True)` for immutability, ensuring data integrity after creation.

### Holiday Detection Strategy
Instead of relying on a potentially unreliable `holidays` attribute in exchange_calendars, we define a holiday as:
> A weekday (Mon-Fri) that is not a trading session

This is more robust and works correctly with the `is_session()` method.

### Cross-Platform Date Formatting
The `format_for_display()` method uses `{day}` instead of `%-d` for cross-platform compatibility (Windows doesn't support `%-d`).

## Acceptance Criteria Met
✅ A single command can fetch a snapshot for a known trading date and return a normalized internal structure
✅ Missing optional fields do not break facts bundle creation (CrossAssetMetrics is fully optional)
✅ Calendar adapter provides trading days, holidays, and half-days
✅ Catalysts have explicit UTC timezone labeling

## Files Changed
- `src/argus/adapters/__init__.py` (new)
- `src/argus/adapters/market_data.py` (new)
- `src/argus/adapters/calendar.py` (new)
- `tests/test_market_data.py` (new)
- `tests/test_calendar.py` (new)
- `pyproject.toml` (updated with dependencies)
