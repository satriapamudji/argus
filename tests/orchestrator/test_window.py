"""Tests for window selection logic."""

from datetime import datetime, date, timedelta
from unittest.mock import MagicMock, patch

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore[import-not-found,no-redef]

from argus.orchestrator.types import RunMode, WindowConfig
from argus.orchestrator.window import (
    TZ_NEW_YORK,
    TZ_SINGAPORE,
    TZ_UTC,
    get_ny_market_close,
    get_ny_market_open,
    get_previous_friday_close,
    get_previous_monday_open,
    get_trading_date_for_run,
    get_window_for_mode,
    get_window_for_monday_preview,
    get_window_for_us_close,
    get_window_for_weekend_wrap,
)


class TestGetNyMarketTimes:
    """Tests for NYSE market time helpers."""

    def test_get_ny_market_close(self):
        """Test market close returns 4:00 PM ET."""
        trading_date = date(2025, 1, 6)  # Monday
        close = get_ny_market_close(trading_date)

        assert close.hour == 16
        assert close.minute == 0
        assert close.tzinfo == TZ_NEW_YORK
        assert close.date() == trading_date

    def test_get_ny_market_open(self):
        """Test market open returns 9:30 AM ET."""
        trading_date = date(2025, 1, 6)  # Monday
        open_time = get_ny_market_open(trading_date)

        assert open_time.hour == 9
        assert open_time.minute == 30
        assert open_time.tzinfo == TZ_NEW_YORK
        assert open_time.date() == trading_date


class TestGetPreviousDays:
    """Tests for previous day calculations."""

    def test_get_previous_friday_close_from_saturday(self):
        """Test finding Friday close from Saturday."""
        saturday = date(2025, 1, 4)  # Saturday
        friday_close = get_previous_friday_close(saturday)

        assert friday_close.date() == date(2025, 1, 3)  # Friday
        assert friday_close.hour == 16
        assert friday_close.tzinfo == TZ_NEW_YORK

    def test_get_previous_friday_close_from_sunday(self):
        """Test finding Friday close from Sunday."""
        sunday = date(2025, 1, 5)  # Sunday
        friday_close = get_previous_friday_close(sunday)

        assert friday_close.date() == date(2025, 1, 3)  # Friday

    def test_get_previous_monday_open_from_saturday(self):
        """Test finding Monday open from Saturday."""
        saturday = date(2025, 1, 4)  # Saturday
        monday_open = get_previous_monday_open(saturday)

        assert monday_open.date() == date(2024, 12, 30)  # Previous Monday
        assert monday_open.hour == 9
        assert monday_open.minute == 30


class TestGetWindowForUsClose:
    """Tests for us_close window calculation."""

    def test_window_is_24_hours(self):
        """Test us_close window is 24 hours."""
        now = datetime(2025, 1, 7, 6, 0, 0, tzinfo=TZ_SINGAPORE)
        window = get_window_for_us_close(now)

        assert window.window_hours == 24
        assert window.mode == RunMode.US_CLOSE

    def test_window_end_is_now(self):
        """Test window ends at current time."""
        now = datetime(2025, 1, 7, 6, 0, 0, tzinfo=TZ_SINGAPORE)
        window = get_window_for_us_close(now)

        assert window.end == now

    def test_window_start_is_24h_before(self):
        """Test window starts 24h before now."""
        now = datetime(2025, 1, 7, 6, 0, 0, tzinfo=TZ_SINGAPORE)
        window = get_window_for_us_close(now)

        expected_start = now - timedelta(hours=24)
        assert window.start == expected_start


class TestGetWindowForWeekendWrap:
    """Tests for weekend_wrap window calculation."""

    def test_window_starts_at_monday_open(self):
        """Test weekend_wrap starts at Monday market open."""
        # Saturday 10:00 SGT
        now = datetime(2025, 1, 4, 10, 0, 0, tzinfo=TZ_SINGAPORE)
        window = get_window_for_weekend_wrap(now)

        assert window.mode == RunMode.WEEKEND_WRAP
        # Monday was Dec 30, 2024
        assert window.start.date() == date(2024, 12, 30)
        assert window.start.hour == 9
        assert window.start.minute == 30

    def test_window_ends_at_now(self):
        """Test weekend_wrap ends at current time."""
        now = datetime(2025, 1, 4, 10, 0, 0, tzinfo=TZ_SINGAPORE)
        window = get_window_for_weekend_wrap(now)

        assert window.end == now


class TestGetWindowForMondayPreview:
    """Tests for monday_preview window calculation."""

    def test_window_is_72_hours(self):
        """Test monday_preview window is 72 hours."""
        # Sunday 18:10 NY
        now = datetime(2025, 1, 5, 18, 10, 0, tzinfo=TZ_NEW_YORK)
        window = get_window_for_monday_preview(now)

        assert window.window_hours == 72
        assert window.mode == RunMode.MONDAY_PREVIEW

    def test_window_end_is_now(self):
        """Test window ends at current time."""
        now = datetime(2025, 1, 5, 18, 10, 0, tzinfo=TZ_NEW_YORK)
        window = get_window_for_monday_preview(now)

        assert window.end == now

    def test_window_start_is_72h_before(self):
        """Test window starts 72h before now."""
        now = datetime(2025, 1, 5, 18, 10, 0, tzinfo=TZ_NEW_YORK)
        window = get_window_for_monday_preview(now)

        expected_start = now - timedelta(hours=72)
        assert window.start == expected_start


class TestGetWindowForMode:
    """Tests for the main get_window_for_mode function."""

    def test_dispatches_to_us_close(self):
        """Test US_CLOSE mode dispatches correctly."""
        now = datetime(2025, 1, 7, 6, 0, 0, tzinfo=TZ_UTC)
        window = get_window_for_mode(RunMode.US_CLOSE, now)

        assert window.mode == RunMode.US_CLOSE
        assert window.window_hours == 24

    def test_dispatches_to_weekend_wrap(self):
        """Test WEEKEND_WRAP mode dispatches correctly."""
        now = datetime(2025, 1, 4, 2, 0, 0, tzinfo=TZ_UTC)  # Sat 10:00 SGT
        window = get_window_for_mode(RunMode.WEEKEND_WRAP, now)

        assert window.mode == RunMode.WEEKEND_WRAP
        assert window.window_hours == 120

    def test_dispatches_to_monday_preview(self):
        """Test MONDAY_PREVIEW mode dispatches correctly."""
        now = datetime(2025, 1, 5, 23, 10, 0, tzinfo=TZ_UTC)  # Sun 18:10 NY
        window = get_window_for_mode(RunMode.MONDAY_PREVIEW, now)

        assert window.mode == RunMode.MONDAY_PREVIEW
        assert window.window_hours == 72

    def test_defaults_to_utc_now(self):
        """Test defaults to current UTC time if not provided."""
        window = get_window_for_mode(RunMode.US_CLOSE)

        assert window.mode == RunMode.US_CLOSE
        assert window.end.tzinfo is not None


class TestGetTradingDateForRun:
    """Tests for trading date calculation."""

    def test_us_close_before_market_close(self):
        """Test trading date for us_close before market close."""
        # 10:00 AM NY (before 4PM close)
        now = datetime(2025, 1, 7, 10, 0, 0, tzinfo=TZ_NEW_YORK)
        trading_date = get_trading_date_for_run(RunMode.US_CLOSE, now)

        # Should be previous day
        assert trading_date == date(2025, 1, 6)

    def test_us_close_after_market_close(self):
        """Test trading date for us_close after market close."""
        # 5:00 PM NY (after 4PM close)
        now = datetime(2025, 1, 7, 17, 0, 0, tzinfo=TZ_NEW_YORK)
        trading_date = get_trading_date_for_run(RunMode.US_CLOSE, now)

        # Should be today
        assert trading_date == date(2025, 1, 7)

    def test_weekend_wrap_returns_friday(self):
        """Test weekend_wrap returns Friday's date."""
        # Saturday 10:00 SGT
        now = datetime(2025, 1, 4, 10, 0, 0, tzinfo=TZ_SINGAPORE)
        trading_date = get_trading_date_for_run(RunMode.WEEKEND_WRAP, now)

        # Should be Friday Jan 3
        assert trading_date == date(2025, 1, 3)
        assert trading_date.weekday() == 4  # Friday

    def test_monday_preview_from_sunday(self):
        """Test monday_preview returns upcoming Monday."""
        # Sunday 18:10 NY
        now = datetime(2025, 1, 5, 18, 10, 0, tzinfo=TZ_NEW_YORK)
        trading_date = get_trading_date_for_run(RunMode.MONDAY_PREVIEW, now)

        # Should be Monday Jan 6
        assert trading_date == date(2025, 1, 6)
        assert trading_date.weekday() == 0  # Monday


class TestDstHandling:
    """Tests for DST-safe timezone handling."""

    def test_window_during_dst_transition(self):
        """Test window calculation during DST transition."""
        # March 9, 2025 is when DST starts in NY (spring forward)
        # Run at 6:00 AM SGT on March 10, 2025
        now = datetime(2025, 3, 10, 6, 0, 0, tzinfo=TZ_SINGAPORE)
        window = get_window_for_us_close(now)

        # Should still work correctly
        assert window.mode == RunMode.US_CLOSE
        assert window.window_hours == 24
        # Window should span 24 hours despite DST change
        diff = window.end - window.start
        assert diff == timedelta(hours=24)

    def test_trading_date_during_dst(self):
        """Test trading date calculation during DST."""
        # During DST, market still closes at 4PM ET
        now = datetime(2025, 7, 1, 17, 0, 0, tzinfo=TZ_NEW_YORK)
        trading_date = get_trading_date_for_run(RunMode.US_CLOSE, now)

        # Should return today since we're after market close
        assert trading_date == date(2025, 7, 1)
