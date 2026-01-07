"""Tests for holiday/half-day behavior handler."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from argus.orchestrator.holiday import (
    DEFAULT_HALF_DAY_BEHAVIORS,
    DEFAULT_HOLIDAY_BEHAVIORS,
    check_holiday_status,
    get_next_trading_date_for_run,
    should_run_monday_preview,
)
from argus.orchestrator.types import (
    HalfDayBehavior,
    HolidayBehavior,
    HolidayInfo,
    RunMode,
)


class TestCheckHolidayStatus:
    """Tests for check_holiday_status function."""

    def test_normal_trading_day(self):
        """Test normal trading day returns no skip."""
        mock_calendar = MagicMock()
        mock_day_info = MagicMock()
        mock_day_info.is_holiday = False
        mock_day_info.is_half_day = False
        mock_day_info.holiday_name = None
        mock_calendar.get_trading_day_info.return_value = mock_day_info

        result = check_holiday_status(
            trading_date=date(2025, 1, 7),
            mode=RunMode.US_CLOSE,
            calendar=mock_calendar,
        )

        assert result.is_holiday is False
        assert result.is_half_day is False
        assert result.should_skip is False

    def test_holiday_with_skip_behavior(self):
        """Test holiday with SKIP behavior."""
        mock_calendar = MagicMock()
        mock_day_info = MagicMock()
        mock_day_info.is_holiday = True
        mock_day_info.is_half_day = False
        mock_day_info.holiday_name = "Christmas"
        mock_calendar.get_trading_day_info.return_value = mock_day_info

        result = check_holiday_status(
            trading_date=date(2025, 12, 25),
            mode=RunMode.US_CLOSE,
            calendar=mock_calendar,
            holiday_behavior=HolidayBehavior.SKIP,
        )

        assert result.is_holiday is True
        assert result.should_skip is True
        assert result.behavior_applied == "skip"

    def test_holiday_with_publish_closed_note(self):
        """Test holiday with PUBLISH_CLOSED_NOTE behavior."""
        mock_calendar = MagicMock()
        mock_day_info = MagicMock()
        mock_day_info.is_holiday = True
        mock_day_info.is_half_day = False
        mock_day_info.holiday_name = "New Year's Day"
        mock_calendar.get_trading_day_info.return_value = mock_day_info

        result = check_holiday_status(
            trading_date=date(2025, 1, 1),
            mode=RunMode.US_CLOSE,
            calendar=mock_calendar,
            holiday_behavior=HolidayBehavior.PUBLISH_CLOSED_NOTE,
        )

        assert result.is_holiday is True
        assert result.should_skip is False
        assert result.behavior_applied == "publish_closed_note"
        assert result.label_text is not None
        assert "Markets Closed" in result.label_text
        assert "New Year's Day" in result.label_text

    def test_half_day_with_label_behavior(self):
        """Test half-day with LABEL_HALF_DAY behavior."""
        mock_calendar = MagicMock()
        mock_day_info = MagicMock()
        mock_day_info.is_holiday = False
        mock_day_info.is_half_day = True
        mock_day_info.holiday_name = None
        mock_calendar.get_trading_day_info.return_value = mock_day_info

        result = check_holiday_status(
            trading_date=date(2025, 12, 24),  # Christmas Eve
            mode=RunMode.US_CLOSE,
            calendar=mock_calendar,
            half_day_behavior=HalfDayBehavior.LABEL_HALF_DAY,
        )

        assert result.is_half_day is True
        assert result.should_skip is False
        assert result.behavior_applied == "label_half_day"
        assert result.label_text is not None
        assert "Early Close" in result.label_text

    def test_half_day_with_skip_behavior(self):
        """Test half-day with SKIP behavior."""
        mock_calendar = MagicMock()
        mock_day_info = MagicMock()
        mock_day_info.is_holiday = False
        mock_day_info.is_half_day = True
        mock_day_info.holiday_name = None
        mock_calendar.get_trading_day_info.return_value = mock_day_info

        result = check_holiday_status(
            trading_date=date(2025, 12, 24),
            mode=RunMode.US_CLOSE,
            calendar=mock_calendar,
            half_day_behavior=HalfDayBehavior.SKIP,
        )

        assert result.is_half_day is True
        assert result.should_skip is True
        assert result.behavior_applied == "skip"

    def test_uses_default_behaviors_per_mode(self):
        """Test defaults are applied per mode."""
        mock_calendar = MagicMock()
        mock_day_info = MagicMock()
        mock_day_info.is_holiday = True
        mock_day_info.is_half_day = False
        mock_day_info.holiday_name = "Holiday"
        mock_calendar.get_trading_day_info.return_value = mock_day_info

        # US_CLOSE default is PUBLISH_CLOSED_NOTE
        result = check_holiday_status(
            trading_date=date(2025, 1, 1),
            mode=RunMode.US_CLOSE,
            calendar=mock_calendar,
        )
        assert result.should_skip is False

        # WEEKEND_WRAP default is SKIP
        result = check_holiday_status(
            trading_date=date(2025, 1, 1),
            mode=RunMode.WEEKEND_WRAP,
            calendar=mock_calendar,
        )
        assert result.should_skip is True


class TestDefaultBehaviors:
    """Tests for default behavior configurations."""

    def test_us_close_defaults(self):
        """Test US_CLOSE default behaviors."""
        assert DEFAULT_HOLIDAY_BEHAVIORS[RunMode.US_CLOSE] == HolidayBehavior.PUBLISH_CLOSED_NOTE
        assert DEFAULT_HALF_DAY_BEHAVIORS[RunMode.US_CLOSE] == HalfDayBehavior.LABEL_HALF_DAY

    def test_weekend_wrap_defaults(self):
        """Test WEEKEND_WRAP default behaviors."""
        assert DEFAULT_HOLIDAY_BEHAVIORS[RunMode.WEEKEND_WRAP] == HolidayBehavior.SKIP
        assert DEFAULT_HALF_DAY_BEHAVIORS[RunMode.WEEKEND_WRAP] == HalfDayBehavior.LABEL_HALF_DAY

    def test_monday_preview_defaults(self):
        """Test MONDAY_PREVIEW default behaviors."""
        assert (
            DEFAULT_HOLIDAY_BEHAVIORS[RunMode.MONDAY_PREVIEW] == HolidayBehavior.PUBLISH_CLOSED_NOTE
        )
        assert DEFAULT_HALF_DAY_BEHAVIORS[RunMode.MONDAY_PREVIEW] == HalfDayBehavior.LABEL_HALF_DAY


class TestGetNextTradingDateForRun:
    """Tests for get_next_trading_date_for_run function."""

    def test_gets_next_trading_day(self):
        """Test returns next trading day for US_CLOSE."""
        mock_calendar = MagicMock()
        mock_calendar.get_next_trading_day.return_value = date(2025, 1, 2)

        result = get_next_trading_date_for_run(
            trading_date=date(2025, 1, 1),  # Holiday
            mode=RunMode.US_CLOSE,
            calendar=mock_calendar,
        )

        assert result == date(2025, 1, 2)

    def test_weekend_wrap_finds_friday(self):
        """Test WEEKEND_WRAP finds next Friday."""
        mock_calendar = MagicMock()
        # Simulate finding next trading days until Friday
        mock_calendar.get_next_trading_day.side_effect = [
            date(2025, 1, 2),  # Thursday
            date(2025, 1, 3),  # Friday
        ]

        result = get_next_trading_date_for_run(
            trading_date=date(2025, 1, 1),  # Wednesday
            mode=RunMode.WEEKEND_WRAP,
            calendar=mock_calendar,
        )

        assert result == date(2025, 1, 3)  # Friday
        assert result.weekday() == 4


class TestShouldRunMondayPreview:
    """Tests for should_run_monday_preview function."""

    def test_returns_true_for_normal_week(self):
        """Test returns True for normal trading week."""
        mock_calendar = MagicMock()
        mock_calendar.get_trading_days_in_range.return_value = [
            date(2025, 1, 6),  # Mon
            date(2025, 1, 7),  # Tue
            date(2025, 1, 8),  # Wed
            date(2025, 1, 9),  # Thu
            date(2025, 1, 10),  # Fri
        ]

        should_run, reason = should_run_monday_preview(
            preview_date=date(2025, 1, 6),
            calendar=mock_calendar,
        )

        assert should_run is True
        assert "5 trading days" in reason

    def test_returns_true_for_short_week(self):
        """Test returns True for short week with reason."""
        mock_calendar = MagicMock()
        mock_calendar.get_trading_days_in_range.return_value = [
            date(2025, 1, 2),  # Thu (Wed is holiday)
            date(2025, 1, 3),  # Fri
        ]

        should_run, reason = should_run_monday_preview(
            preview_date=date(2024, 12, 30),  # Week with NY Day
            calendar=mock_calendar,
        )

        assert should_run is True
        assert "Short week" in reason

    def test_returns_false_for_no_trading_days(self):
        """Test returns False when no trading days in week."""
        mock_calendar = MagicMock()
        mock_calendar.get_trading_days_in_range.return_value = []

        should_run, reason = should_run_monday_preview(
            preview_date=date(2025, 1, 6),
            calendar=mock_calendar,
        )

        assert should_run is False
        assert "No trading days" in reason
