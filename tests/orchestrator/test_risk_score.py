"""Tests for risk score calculator."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from argus.adapters.market_data import HistoricalMetrics
from argus.orchestrator.risk_score import (
    CALENDAR_SCORE_RULES,
    HIGH_IMPACT_TOPICS,
    POLITICAL_KEYWORDS,
    CalendarScoreDetails,
    HeadlineScoreDetails,
    MarketScoreDetails,
    calculate_calendar_score,
    calculate_headline_score,
    calculate_market_score,
    calculate_risk_score,
)
from argus.orchestrator.types import RiskScoreBreakdown


class TestCalendarScoreDetails:
    """Tests for CalendarScoreDetails."""

    def test_total_sums_all_components(self):
        """Test total is sum of all components."""
        details = CalendarScoreDetails(
            central_bank_pts=25,
            inflation_pts=20,
            jobs_pts=15,
        )
        assert details.total == 60  # Capped at 60

    def test_total_capped_at_60(self):
        """Test total is capped at 60."""
        details = CalendarScoreDetails(
            central_bank_pts=25,
            inflation_pts=20,
            jobs_pts=15,
            gdp_ism_pts=10,  # Would exceed 60
        )
        assert details.total == 60


class TestMarketScoreDetails:
    """Tests for MarketScoreDetails."""

    def test_total_sums_all_components(self):
        """Test total is sum of all components."""
        details = MarketScoreDetails(
            vix_pts=30,
            sp500_pts=20,
            us10y_pts=12,
        )
        # Would be 62, but capped at 30
        assert details.total == 30

    def test_total_capped_at_30(self):
        """Test total is capped at 30."""
        details = MarketScoreDetails(
            vix_pts=10,
            sp500_pts=10,
            us10y_pts=8,
        )
        assert details.total == 28


class TestHeadlineScoreDetails:
    """Tests for HeadlineScoreDetails."""

    def test_total_is_10_per_item(self):
        """Test each high-impact item is 10 points."""
        details = HeadlineScoreDetails(high_impact_count=2)
        assert details.total == 20

    def test_total_capped_at_30(self):
        """Test total is capped at 30."""
        details = HeadlineScoreDetails(high_impact_count=5)
        assert details.total == 30


class TestCalculateMarketScore:
    """Tests for calculate_market_score function."""

    def test_vix_scoring_tiers(self):
        """Test VIX scoring at different levels."""
        # VIX >= 30 -> 30 pts
        metrics = HistoricalMetrics(vix_current=Decimal("32.5"))
        details = calculate_market_score(metrics)
        assert details.vix_pts == 30

        # VIX >= 25 -> 20 pts
        metrics = HistoricalMetrics(vix_current=Decimal("27.0"))
        details = calculate_market_score(metrics)
        assert details.vix_pts == 20

        # VIX >= 20 -> 10 pts
        metrics = HistoricalMetrics(vix_current=Decimal("22.0"))
        details = calculate_market_score(metrics)
        assert details.vix_pts == 10

        # VIX < 20 -> 0 pts
        metrics = HistoricalMetrics(vix_current=Decimal("15.0"))
        details = calculate_market_score(metrics)
        assert details.vix_pts == 0

    def test_sp500_scoring_tiers(self):
        """Test S&P 500 5D return scoring."""
        # <= -5% -> 20 pts
        metrics = HistoricalMetrics(sp500_5d_return_pct=Decimal("-6.5"))
        details = calculate_market_score(metrics)
        assert details.sp500_pts == 20

        # <= -3% -> 10 pts
        metrics = HistoricalMetrics(sp500_5d_return_pct=Decimal("-3.5"))
        details = calculate_market_score(metrics)
        assert details.sp500_pts == 10

        # > -3% -> 0 pts
        metrics = HistoricalMetrics(sp500_5d_return_pct=Decimal("-1.0"))
        details = calculate_market_score(metrics)
        assert details.sp500_pts == 0

    def test_us10y_scoring_tiers(self):
        """Test US10Y 5D move scoring."""
        # >= 30 bps -> 12 pts
        metrics = HistoricalMetrics(us10y_5d_move_bps=Decimal("35.0"))
        details = calculate_market_score(metrics)
        assert details.us10y_pts == 12

        # >= 20 bps -> 8 pts
        metrics = HistoricalMetrics(us10y_5d_move_bps=Decimal("25.0"))
        details = calculate_market_score(metrics)
        assert details.us10y_pts == 8

        # < 20 bps -> 0 pts
        metrics = HistoricalMetrics(us10y_5d_move_bps=Decimal("15.0"))
        details = calculate_market_score(metrics)
        assert details.us10y_pts == 0

    def test_combined_high_stress_scenario(self):
        """Test combined high stress market scenario."""
        metrics = HistoricalMetrics(
            vix_current=Decimal("35.0"),  # 30 pts
            sp500_5d_return_pct=Decimal("-7.0"),  # 20 pts
            us10y_5d_move_bps=Decimal("40.0"),  # 12 pts
        )
        details = calculate_market_score(metrics)

        assert details.vix_pts == 30
        assert details.sp500_pts == 20
        assert details.us10y_pts == 12
        # Total capped at 30
        assert details.total == 30

    def test_handles_none_values(self):
        """Test graceful handling of None values."""
        metrics = HistoricalMetrics()  # All None
        details = calculate_market_score(metrics)

        assert details.vix_pts == 0
        assert details.sp500_pts == 0
        assert details.us10y_pts == 0
        assert details.total == 0


class TestCalculateCalendarScore:
    """Tests for calculate_calendar_score function."""

    def test_with_mock_fomc_event(self):
        """Test FOMC event scores 25 points."""
        mock_conn = MagicMock()

        # Mock event row
        mock_event = MagicMock()
        mock_event.title = "FOMC Rate Decision"

        with patch(
            "argus.orchestrator.risk_score.get_upcoming_events",
            return_value=[mock_event],
        ):
            now = datetime.now(timezone.utc)
            details = calculate_calendar_score(
                mock_conn,
                window_start=now - timedelta(hours=72),
                window_end=now,
            )

        assert details.central_bank_pts == 25
        assert details.total >= 25

    def test_with_mock_cpi_event(self):
        """Test CPI event scores 20 points."""
        mock_conn = MagicMock()

        mock_event = MagicMock()
        mock_event.title = "CPI m/m"

        with patch(
            "argus.orchestrator.risk_score.get_upcoming_events",
            return_value=[mock_event],
        ):
            now = datetime.now(timezone.utc)
            details = calculate_calendar_score(
                mock_conn,
                window_start=now - timedelta(hours=72),
                window_end=now,
            )

        assert details.inflation_pts == 20

    def test_with_mock_jobs_event(self):
        """Test Nonfarm Payrolls scores 15 points."""
        mock_conn = MagicMock()

        mock_event = MagicMock()
        mock_event.title = "Nonfarm Payrolls"

        with patch(
            "argus.orchestrator.risk_score.get_upcoming_events",
            return_value=[mock_event],
        ):
            now = datetime.now(timezone.utc)
            details = calculate_calendar_score(
                mock_conn,
                window_start=now - timedelta(hours=72),
                window_end=now,
            )

        assert details.jobs_pts == 15

    def test_multiple_events(self):
        """Test multiple events contribute to score."""
        mock_conn = MagicMock()

        events = [
            MagicMock(title="FOMC Rate Decision"),
            MagicMock(title="CPI m/m"),
            MagicMock(title="Nonfarm Payrolls"),
        ]

        with patch(
            "argus.orchestrator.risk_score.get_upcoming_events",
            return_value=events,
        ):
            now = datetime.now(timezone.utc)
            details = calculate_calendar_score(
                mock_conn,
                window_start=now - timedelta(hours=72),
                window_end=now,
            )

        assert details.central_bank_pts == 25
        assert details.inflation_pts == 20
        assert details.jobs_pts == 15
        assert details.total == 60  # Capped at 60

    def test_handles_fetch_error(self):
        """Test graceful handling of database errors."""
        mock_conn = MagicMock()

        with patch(
            "argus.orchestrator.risk_score.get_upcoming_events",
            side_effect=Exception("DB error"),
        ):
            now = datetime.now(timezone.utc)
            details = calculate_calendar_score(
                mock_conn,
                window_start=now - timedelta(hours=72),
                window_end=now,
            )

        assert details.total == 0


class TestCalculateHeadlineScore:
    """Tests for calculate_headline_score function."""

    def test_high_impact_geopolitics(self):
        """Test high-impact geopolitics news scores points."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            (1, "Major Geopolitical Event", 85, "geopolitics"),
        ]

        now = datetime.now(timezone.utc)
        details = calculate_headline_score(
            mock_conn,
            window_start=now - timedelta(hours=72),
            window_end=now,
        )

        assert details.high_impact_count == 1
        assert details.total == 10

    def test_three_high_impact_caps_at_30(self):
        """Test 3+ high-impact items caps at 30."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            (1, "Event 1", 90, "geopolitics"),
            (2, "Event 2", 85, "systemic"),
            (3, "Event 3", 82, "policy"),
            (4, "Event 4", 80, "credit"),  # Won't be counted
        ]

        now = datetime.now(timezone.utc)
        details = calculate_headline_score(
            mock_conn,
            window_start=now - timedelta(hours=72),
            window_end=now,
        )

        assert details.high_impact_count == 3
        assert details.total == 30

    def test_non_high_impact_topics_ignored(self):
        """Test non-high-impact topics don't score."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            (1, "Tech Earnings", 85, "earnings"),  # Not in HIGH_IMPACT_TOPICS
            (2, "Market Update", 82, "markets"),  # Not in HIGH_IMPACT_TOPICS
        ]

        now = datetime.now(timezone.utc)
        details = calculate_headline_score(
            mock_conn,
            window_start=now - timedelta(hours=72),
            window_end=now,
        )

        assert details.high_impact_count == 0
        assert details.total == 0


class TestCalculateRiskScore:
    """Tests for calculate_risk_score main function."""

    def test_combines_all_components(self):
        """Test risk score combines all three components."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        # Mock market data
        mock_metrics = HistoricalMetrics(
            vix_current=Decimal("25.0"),  # 20 pts
            sp500_5d_return_pct=Decimal("-4.0"),  # 10 pts
        )

        # Mock calendar events
        with patch(
            "argus.orchestrator.risk_score.get_upcoming_events",
            return_value=[MagicMock(title="CPI m/m")],  # 20 pts
        ):
            now = datetime.now(timezone.utc)
            breakdown = calculate_risk_score(
                conn=mock_conn,
                window_start=now - timedelta(hours=72),
                window_end=now,
                historical_metrics=mock_metrics,
            )

        assert isinstance(breakdown, RiskScoreBreakdown)
        assert breakdown.calendar_score == 20
        assert breakdown.market_score == 30  # 20+10, but capped at 30
        assert breakdown.headline_score == 0
        assert breakdown.total == 50  # 20 + 30 + 0

    def test_total_capped_at_100(self):
        """Test total risk score capped at 100."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        # Mock headline returns 3 high-impact items
        mock_cursor.fetchall.return_value = [
            (1, "Event 1", 90, "geopolitics"),
            (2, "Event 2", 85, "systemic"),
            (3, "Event 3", 82, "policy"),
        ]

        # Max market metrics
        mock_metrics = HistoricalMetrics(
            vix_current=Decimal("35.0"),  # 30 pts
            sp500_5d_return_pct=Decimal("-6.0"),  # 20 pts
            us10y_5d_move_bps=Decimal("35.0"),  # 12 pts
        )

        # Max calendar events
        with patch(
            "argus.orchestrator.risk_score.get_upcoming_events",
            return_value=[
                MagicMock(title="FOMC Rate Decision"),  # 25
                MagicMock(title="CPI m/m"),  # 20
                MagicMock(title="Nonfarm Payrolls"),  # 15
            ],
        ):
            now = datetime.now(timezone.utc)
            breakdown = calculate_risk_score(
                conn=mock_conn,
                window_start=now - timedelta(hours=72),
                window_end=now,
                historical_metrics=mock_metrics,
            )

        # calendar=60, market=30, headline=30 = 120, capped at 100
        assert breakdown.total == 100

    def test_includes_details(self):
        """Test breakdown includes detailed information."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        mock_metrics = HistoricalMetrics(vix_current=Decimal("22.0"))

        with patch(
            "argus.orchestrator.risk_score.get_upcoming_events",
            return_value=[],
        ):
            now = datetime.now(timezone.utc)
            breakdown = calculate_risk_score(
                conn=mock_conn,
                window_start=now - timedelta(hours=72),
                window_end=now,
                historical_metrics=mock_metrics,
            )

        assert breakdown.details is not None
        assert "calendar" in breakdown.details
        assert "market" in breakdown.details
        assert "headline" in breakdown.details
