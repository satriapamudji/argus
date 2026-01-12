"""Tests for weekly stats computation.

These tests validate the pure weekly return logic in argus.orchestrator.weekly_stats.
No database access required.
"""

from __future__ import annotations

from datetime import date

import pytest

from argus.orchestrator.weekly_stats import compute_weekly_stats


def _snapshot(
    trading_date: date,
    *,
    sp500_close: float | None,
    dow_close: float | None,
    nasdaq_close: float | None,
) -> dict:
    return {
        "trading_date": trading_date,
        "sp500_close": sp500_close,
        "dow_close": dow_close,
        "nasdaq_close": nasdaq_close,
    }


class TestComputeWeeklyStats:
    def test_prefers_fri_fri_when_prior_anchor_exists(self) -> None:
        # Week: Mon 2025-01-06 to Fri 2025-01-10
        week_start = date(2025, 1, 6)
        week_end = date(2025, 1, 10)

        week = [
            _snapshot(date(2025, 1, 6), sp500_close=100.0, dow_close=200.0, nasdaq_close=300.0),
            _snapshot(date(2025, 1, 10), sp500_close=110.0, dow_close=220.0, nasdaq_close=330.0),
        ]
        prior_anchor = _snapshot(
            date(2025, 1, 3), sp500_close=95.0, dow_close=190.0, nasdaq_close=285.0
        )

        stats = compute_weekly_stats(
            week_start=week_start,
            week_end=week_end,
            week_snapshots=week,
            prior_anchor_snapshot=prior_anchor,
        )

        assert stats.week_start == week_start
        assert stats.week_end == week_end

        assert stats.sp500_return is not None
        assert stats.sp500_return.label == "Fri/Fri"
        assert stats.sp500_return.start_date == date(2025, 1, 3)
        assert stats.sp500_return.end_date == date(2025, 1, 10)
        assert stats.sp500_return.return_pct == pytest.approx(((110.0 - 95.0) / 95.0) * 100.0)

    def test_falls_back_to_week_start_when_no_prior_anchor(self) -> None:
        week_start = date(2025, 1, 6)
        week_end = date(2025, 1, 10)

        week = [
            _snapshot(date(2025, 1, 6), sp500_close=100.0, dow_close=200.0, nasdaq_close=300.0),
            _snapshot(date(2025, 1, 10), sp500_close=110.0, dow_close=220.0, nasdaq_close=330.0),
        ]

        stats = compute_weekly_stats(
            week_start=week_start,
            week_end=week_end,
            week_snapshots=week,
            prior_anchor_snapshot=None,
        )

        assert stats.sp500_return is not None
        assert stats.sp500_return.label == "Mon/Fri"
        assert stats.sp500_return.start_date == date(2025, 1, 6)
        assert stats.sp500_return.end_date == date(2025, 1, 10)
        assert stats.sp500_return.return_pct == pytest.approx(10.0)

    def test_partial_week_single_snapshot(self) -> None:
        week_start = date(2025, 1, 6)
        week_end = date(2025, 1, 10)

        week = [
            _snapshot(date(2025, 1, 10), sp500_close=110.0, dow_close=220.0, nasdaq_close=330.0)
        ]

        stats = compute_weekly_stats(
            week_start=week_start,
            week_end=week_end,
            week_snapshots=week,
            prior_anchor_snapshot=None,
        )

        assert stats.sp500_return is not None
        assert stats.sp500_return.label == "Partial"
        assert stats.sp500_return.start_date == date(2025, 1, 10)
        assert stats.sp500_return.end_date == date(2025, 1, 10)
        assert stats.sp500_return.return_pct == pytest.approx(0.0)

    def test_missing_close_returns_none_for_that_index(self) -> None:
        week_start = date(2025, 1, 6)
        week_end = date(2025, 1, 10)

        week = [
            _snapshot(date(2025, 1, 6), sp500_close=100.0, dow_close=200.0, nasdaq_close=None),
            _snapshot(date(2025, 1, 10), sp500_close=110.0, dow_close=220.0, nasdaq_close=None),
        ]

        stats = compute_weekly_stats(
            week_start=week_start,
            week_end=week_end,
            week_snapshots=week,
            prior_anchor_snapshot=None,
        )

        assert stats.sp500_return is not None
        assert stats.dow_return is not None
        assert stats.nasdaq_return is None
