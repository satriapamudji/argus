# Task 12: Build run orchestrator + scheduling hooks

## Goal
Implement end-to-end runs (`us_close`, `weekend_wrap`, `monday_preview`) with DST-safe scheduling assumptions.

## Dependencies
- Depends on Task 01
- Depends on Task 02
- Depends on Task 03
- Depends on Task 05
- Depends on Task 06
- Depends on Task 07
- Depends on Task 08
- Depends on Task 09
- Depends on Task 10
- Depends on Task 11

## References
- `tasks/01_plan/spec.md` ((4) Scheduling & Timezones, (4) risk_score definition, (4) US Holidays & Half-days, (8) Architecture: Run Orchestrator)

## Scope
- `bin/argus run --stream us_close_basic --mode <mode>` performs:
  1) window selection
  2) shortlist + enrichment (optional)
  3) scoring + selection
  4) facts bundle creation
  5) generation + validation
  6) publish (optional)
- Implement `--conditional true` for `monday_preview` using `risk_score >= threshold`.
- Respect holiday/half-day behaviors from `tasks/01_plan/spec.md` (NYSE calendar + configured behavior).

## Acceptance criteria
- Each run mode completes with a persisted `run` artifact even if publishing is disabled.
- Cron examples in `tasks/01_plan/spec.md` map cleanly to CLI invocations.

---

## Implementation Notes (Completed)

### Files Created

#### `src/argus/orchestrator/` module:
- **`types.py`** - Core types:
  - `RunMode` enum: `US_CLOSE`, `WEEKEND_WRAP`, `MONDAY_PREVIEW`
  - `RunStatus` enum: `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `SKIPPED`
  - `HolidayBehavior` enum: `SKIP`, `PUBLISH_CLOSED_NOTE`
  - `HalfDayBehavior` enum: `SKIP`, `LABEL_HALF_DAY`
  - `WindowConfig` dataclass: `start`, `end`, `hours`
  - `RiskScoreBreakdown` dataclass: `calendar_score`, `market_score`, `headline_score`, `total`, `details`
  - `RunTimings` dataclass: `ingest_ms`, `score_ms`, `enrich_ms`, `bundle_ms`, `generate_ms`, `validate_ms`, `publish_ms`, `total_ms`
  - `HolidayInfo` dataclass: `is_holiday`, `is_half_day`, `holiday_name`, `should_skip`, `behavior_applied`
  - `RunResult` dataclass: Complete run result with all metadata

- **`window.py`** - DST-safe window selection:
  - `get_window_for_mode(mode, now)` → Returns `WindowConfig` with appropriate lookback
  - `get_trading_date_for_run(mode, now)` → Returns the trading date this run covers
  - Window sizes: `us_close` = 24h, `weekend_wrap` = Mon-Fri, `monday_preview` = 72h

- **`risk_score.py`** - Risk score calculation for monday_preview:
  - `calculate_calendar_score(events)` → 0-60 pts based on upcoming economic events
  - `calculate_market_score(historical)` → 0-30 pts based on VIX, S&P 5D change, US10Y 5D change
  - `calculate_headline_score(news_items)` → 0-30 pts based on high-impact news count
  - `calculate_risk_score(events, historical, news_items)` → Combined `RiskScoreBreakdown`
  - Calendar scoring: FOMC +25, CPI/PCE +20, Jobs +15, GDP/ISM +10, Treasury +8, Political +15
  - Market scoring: VIX ≥30 → +30, S&P 5D ≤-5% → +20, US10Y 5D ≥30bps → +12

- **`holiday.py`** - Holiday/half-day behavior handler:
  - `check_holiday_status(trading_date)` → Returns `HolidayInfo` using NYSE calendar
  - `should_run_monday_preview(trading_date)` → Checks if Monday is a trading day
  - `get_next_trading_date_for_run(mode, now)` → Finds next valid trading date

- **`orchestrator.py`** - Main run orchestrator:
  - `OrchestratorOptions` dataclass with all run flags
  - `RunOrchestrator` class that executes the full pipeline:
    1. Check holiday/half-day status → apply behavior
    2. Optional ingestion (if `--include-ingest`)
    3. Optional scoring (if not `--skip-scoring`)
    4. Optional enrichment (if not `--skip-enrichment`)
    5. Calculate risk score (for monday_preview)
    6. Check conditional gate (if `--conditional`)
    7. Build facts bundle
    8. Generate message via LLM
    9. Validate message
    10. Create run + message records
    11. Optional publish (if not `--skip-publish`)
    12. Update run status + timings

### Files Modified

- **`src/argus/adapters/market_data.py`**:
  - Added `HistoricalMetrics` dataclass for 7-day historical data
  - Added `fetch_historical(days=7)` method returning VIX, S&P 500, US10Y historical data

- **`src/argus/config.py`**:
  - Added `HolidayBehaviorConfig` dataclass with `holiday_behavior` and `half_day_behavior` settings
  - Added to `StreamConfig` and YAML parsing in `ArgusConfig.load()`

- **`src/argus/cli.py`**:
  - Updated `run` command with new flags:
    - `--skip-publish`: Run pipeline but don't send to Telegram
    - `--skip-scoring`: Assume items are already scored
    - `--skip-enrichment`: Assume items are already enriched
    - `--include-ingest`: Trigger ingestion before pipeline
    - `--conditional`: For monday_preview, check risk_score threshold
    - `--force-publish`: Override conditional check (always publish)
    - `--force-skip`: Override conditional check (never publish)
  - Full pipeline execution with result reporting and risk score breakdown display

### Tests Created

- **`tests/orchestrator/test_window.py`** - 22 tests:
  - Window selection for all modes
  - DST handling (EDT/EST transitions)
  - Trading date calculation
  - Weekend handling for weekend_wrap

- **`tests/orchestrator/test_risk_score.py`** - 23 tests:
  - Calendar score calculation for all event types
  - Market score calculation with various thresholds
  - Headline score calculation
  - Combined risk score with cap at 100

- **`tests/orchestrator/test_holiday.py`** - 14 tests:
  - Holiday detection using NYSE calendar
  - Half-day detection
  - Should-skip logic based on behavior config
  - Monday preview eligibility

### Config Options

Add to `config.yaml`:
```yaml
stream:
  holiday_behavior:
    holiday_behavior: "skip"  # or "publish_closed_note"
    half_day_behavior: "label_half_day"  # or "skip"
```

### CLI Usage Examples

```bash
# Basic dry run to see configuration
argus run --stream us_close_basic --mode us_close --dry-run

# Full execution
argus run --stream us_close_basic --mode us_close

# Skip publishing (generate message but don't send)
argus run --stream us_close_basic --mode us_close --skip-publish

# Monday preview with conditional gate
argus run --stream us_close_basic --mode monday_preview --conditional

# Force publish monday preview regardless of risk score
argus run --stream us_close_basic --mode monday_preview --force-publish

# Include fresh ingestion before run
argus run --stream us_close_basic --mode us_close --include-ingest
```

### Risk Score Formula

```
risk_score = min(100, calendar_score + market_score + headline_score)

calendar_score (0-60):
  - FOMC: +25
  - CPI/PCE: +20
  - Jobs report: +15
  - GDP/ISM: +10
  - Treasury auction: +8
  - Political event: +15

market_score (0-30):
  - VIX ≥ 30: +30
  - VIX ≥ 25: +20
  - VIX ≥ 20: +10
  - S&P 5D ≤ -5%: +20
  - S&P 5D ≤ -3%: +12
  - US10Y 5D ≥ 30bps: +12
  - US10Y 5D ≥ 20bps: +8

headline_score (0-30):
  - Each high-impact news item: +10 (cap 30)
```

### Test Results

- **472 tests passed, 2 skipped** (full test suite)
- **59 tests passed** (orchestrator tests only)
- ruff: All checks passed
- mypy: 1 minor warning (untyped external call - acceptable)
