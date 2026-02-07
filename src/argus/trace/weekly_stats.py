"""DB-free weekly stats computation for trace module.

Fetches historical market data via yfinance to compute weekly returns
without requiring database access to daily_market_snapshots.
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Optional

from argus.facts_bundle.types import WeeklyReturnBundle, WeeklyStatsBundle
from argus.orchestrator.weekly_stats import WeeklyReturn, WeeklyStats

logger = logging.getLogger(__name__)


def _get_yfinance() -> Any:
    """Lazy-load yfinance module."""
    try:
        import yfinance as yf

        return yf
    except ImportError as e:
        raise ImportError(
            "yfinance is required for market data. Install with: pip install yfinance"
        ) from e


def _previous_week_friday(reference_date: date) -> date:
    """Get the most recent Friday on or before reference_date."""
    days_since_friday = (reference_date.weekday() - 4) % 7
    return reference_date - timedelta(days=days_since_friday)


def _monday_of_week(reference_date: date) -> date:
    """Get Monday for the week containing reference_date."""
    return reference_date - timedelta(days=reference_date.weekday())


@dataclass
class WeeklySnapshotData:
    """Lightweight snapshot for weekly return calculation."""

    trading_date: date
    sp500_close: Optional[float]
    dow_close: Optional[float]
    nasdaq_close: Optional[float]


def fetch_weekly_snapshots(
    week_start: date,
    week_end: date,
) -> tuple[list[WeeklySnapshotData], Optional[WeeklySnapshotData]]:
    """Fetch market snapshots for a week from yfinance.

    Args:
        week_start: Monday of the target week.
        week_end: Friday of the target week.

    Returns:
        Tuple of (week_snapshots sorted ascending, prior_anchor_snapshot or None).
        The prior_anchor is the last trading day before week_start (typically prior Friday).
    """
    yf = _get_yfinance()

    # Extend range to include prior week for anchor
    fetch_start = week_start - timedelta(days=7)
    fetch_end = week_end + timedelta(days=1)  # yfinance end is exclusive

    symbols = {
        "sp500": "^GSPC",
        "dow": "^DJI",
        "nasdaq": "^IXIC",
    }

    # Fetch all indices
    history_data: dict[str, dict[date, float]] = {}

    for key, symbol in symbols.items():
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=fetch_start, end=fetch_end)

            if hist.empty:
                logger.warning(f"No history data for {symbol}")
                continue

            history_data[key] = {}
            for idx, row in hist.iterrows():
                trading_date = idx.date()
                close_price = float(row["Close"])
                history_data[key][trading_date] = close_price

        except Exception as e:
            logger.error(f"Failed to fetch {symbol} history: {e}")
            continue

    if not history_data:
        return [], None

    # Collect all trading dates across indices
    all_dates: set[date] = set()
    for key_data in history_data.values():
        all_dates.update(key_data.keys())

    # Build snapshots
    all_snapshots: list[WeeklySnapshotData] = []
    for trading_date in sorted(all_dates):
        snapshot = WeeklySnapshotData(
            trading_date=trading_date,
            sp500_close=history_data.get("sp500", {}).get(trading_date),
            dow_close=history_data.get("dow", {}).get(trading_date),
            nasdaq_close=history_data.get("nasdaq", {}).get(trading_date),
        )
        all_snapshots.append(snapshot)

    # Split into week snapshots and prior anchor
    week_snapshots = [s for s in all_snapshots if week_start <= s.trading_date <= week_end]

    # Prior anchor: last snapshot strictly before week_start
    prior_candidates = [s for s in all_snapshots if s.trading_date < week_start]
    prior_anchor = prior_candidates[-1] if prior_candidates else None

    return week_snapshots, prior_anchor


def _snapshot_to_dict(snapshot: WeeklySnapshotData) -> dict[str, Any]:
    """Convert snapshot to dict for compute_weekly_stats compatibility."""
    return {
        "trading_date": snapshot.trading_date,
        "sp500_close": snapshot.sp500_close,
        "dow_close": snapshot.dow_close,
        "nasdaq_close": snapshot.nasdaq_close,
    }


def fetch_weekly_stats(
    run_mode: str,
    trading_date: date,
) -> Optional[WeeklyStatsBundle]:
    """Fetch and compute weekly stats for recap/preview modes (DB-free).

    Args:
        run_mode: One of 'weekend_wrap', 'monday_preview', etc.
        trading_date: The trading date for the run.

    Returns:
        WeeklyStatsBundle if data available and mode requires it, None otherwise.
    """
    if run_mode not in {"weekend_wrap", "monday_preview"}:
        return None

    # Calculate target week
    if run_mode == "weekend_wrap":
        week_end = _previous_week_friday(trading_date)
    else:
        # monday_preview: prior week ends previous Friday
        week_end = _previous_week_friday(trading_date - timedelta(days=1))

    week_start = _monday_of_week(week_end)

    try:
        week_snapshots, prior_anchor = fetch_weekly_snapshots(week_start, week_end)
    except Exception as e:
        logger.error(f"Failed to fetch weekly snapshots: {e}")
        return None

    if not week_snapshots:
        logger.warning(f"No weekly snapshots found for {week_start} to {week_end}")
        return None

    # Convert to dicts for compute_weekly_stats
    week_rows = [_snapshot_to_dict(s) for s in week_snapshots]
    prior_anchor_row = _snapshot_to_dict(prior_anchor) if prior_anchor else None

    # Use the existing pure logic function
    from argus.orchestrator.weekly_stats import compute_weekly_stats

    stats_obj = compute_weekly_stats(
        week_start=week_start,
        week_end=week_end,
        week_snapshots=week_rows,
        prior_anchor_snapshot=prior_anchor_row,
    )

    return WeeklyStatsBundle.from_weekly_stats(stats_obj)
