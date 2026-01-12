"""Weekly stats computation from persisted daily market snapshots.

Purpose:
- Provide a compact, cold-start safe set of weekly performance metrics.
- Used by weekend_wrap (weekly recap) and monday_preview (prior week context).

Return definition:
- Primary: Friday close vs prior Friday close.
- Fallback (cold start): Mon->Fri based on available closes.
- Partial weeks: earliest->latest available closes.

This module is intentionally pure logic and expects snapshots to be pulled via
repository helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Optional


@dataclass(frozen=True)
class WeeklyReturn:
    label: str  # 'Fri/Fri', 'Mon/Fri', or 'Partial'
    start_date: date
    end_date: date
    return_pct: float


@dataclass(frozen=True)
class WeeklyStats:
    week_start: date
    week_end: date

    sp500_return: Optional[WeeklyReturn]
    dow_return: Optional[WeeklyReturn]
    nasdaq_return: Optional[WeeklyReturn]


def _pct_change(start: float, end: float) -> float:
    if start == 0:
        raise ValueError("start cannot be 0")
    return ((end - start) / start) * 100.0


def _choose_weekly_return(
    *,
    week_snapshots: list[dict[str, Any]],
    prior_anchor: Optional[dict[str, Any]],
    key_close: str,
) -> Optional[WeeklyReturn]:
    """Choose the weekly return series for one instrument.

    week_snapshots must be sorted ascending by trading_date.
    """

    if not week_snapshots:
        return None

    end = week_snapshots[-1]
    end_close = end.get(key_close)
    if end_close is None:
        return None

    # Primary: Fri/Fri if we have a prior anchor close.
    if prior_anchor is not None:
        start_close = prior_anchor.get(key_close)
        if start_close is not None:
            return WeeklyReturn(
                label="Fri/Fri",
                start_date=prior_anchor["trading_date"],
                end_date=end["trading_date"],
                return_pct=_pct_change(float(start_close), float(end_close)),
            )

    # Fallback: use first available close of the week.
    start = week_snapshots[0]
    start_close = start.get(key_close)
    if start_close is None:
        return None

    label = "Mon/Fri" if len(week_snapshots) >= 2 else "Partial"
    return WeeklyReturn(
        label=label,
        start_date=start["trading_date"],
        end_date=end["trading_date"],
        return_pct=_pct_change(float(start_close), float(end_close)),
    )


def compute_weekly_stats(
    *,
    week_start: date,
    week_end: date,
    week_snapshots: list[dict[str, Any]],
    prior_anchor_snapshot: Optional[dict[str, Any]],
) -> WeeklyStats:
    """Compute weekly stats from snapshot rows.

    Args:
        week_start: Monday of the target week (calendar week for the stream).
        week_end: Friday of the target week.
        week_snapshots: Snapshot dicts within the week (inclusive), ascending.
        prior_anchor_snapshot: The prior Friday (or last available) snapshot strictly
            before week_start; may be None (cold start).

    Returns:
        WeeklyStats with index returns where possible.
    """

    # Ensure sorted for predictable behavior.
    week_snapshots_sorted = sorted(week_snapshots, key=lambda r: r["trading_date"])

    return WeeklyStats(
        week_start=week_start,
        week_end=week_end,
        sp500_return=_choose_weekly_return(
            week_snapshots=week_snapshots_sorted,
            prior_anchor=prior_anchor_snapshot,
            key_close="sp500_close",
        ),
        dow_return=_choose_weekly_return(
            week_snapshots=week_snapshots_sorted,
            prior_anchor=prior_anchor_snapshot,
            key_close="dow_close",
        ),
        nasdaq_return=_choose_weekly_return(
            week_snapshots=week_snapshots_sorted,
            prior_anchor=prior_anchor_snapshot,
            key_close="nasdaq_close",
        ),
    )
