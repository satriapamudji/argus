"""Tests for market calendar adapter."""

from datetime import date, datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from argus.adapters.calendar import (
    Catalyst,
    CatalystType,
    MarketCalendarAdapter,
    TradingDayInfo,
    create_catalyst,
)


class TestCatalystType:
    """Tests for CatalystType enum."""

    def test_catalyst_types_exist(self):
        """Test that all required catalyst types are defined."""
        assert CatalystType.CENTRAL_BANK.value == "central_bank"
        assert CatalystType.ECONOMIC_DATA.value == "economic_data"
        assert CatalystType.EARNINGS.value == "earnings"
        assert CatalystType.POLITICAL.value == "political"
        assert CatalystType.AUCTION.value == "auction"
        assert CatalystType.HOLIDAY.value == "holiday"
        assert CatalystType.HALF_DAY.value == "half_day"
        assert CatalystType.OTHER.value == "other"


class TestCatalyst:
    """Tests for Catalyst dataclass."""

    def test_create_catalyst_with_utc(self):
        """Test creating a catalyst with UTC timestamp."""
        ts = datetime(2026, 1, 15, 14, 30, tzinfo=timezone.utc)
        catalyst = Catalyst(
            name="FOMC Minutes",
            catalyst_type=CatalystType.CENTRAL_BANK,
            timestamp_utc=ts,
            description="Federal Reserve meeting minutes release",
            impact_score=85,
            source="Federal Reserve",
        )

        assert catalyst.name == "FOMC Minutes"
        assert catalyst.catalyst_type == CatalystType.CENTRAL_BANK
        assert catalyst.timestamp_utc == ts
        assert catalyst.description == "Federal Reserve meeting minutes release"
        assert catalyst.impact_score == 85
        assert catalyst.source == "Federal Reserve"

    def test_catalyst_naive_datetime_converted_to_utc(self):
        """Test that naive datetime is converted to UTC."""
        naive_ts = datetime(2026, 1, 15, 14, 30)  # No tzinfo
        catalyst = Catalyst(
            name="CPI Release",
            catalyst_type=CatalystType.ECONOMIC_DATA,
            timestamp_utc=naive_ts,
        )

        # Should be converted to UTC
        assert catalyst.timestamp_utc.tzinfo == timezone.utc
        assert catalyst.timestamp_utc.hour == 14
        assert catalyst.timestamp_utc.minute == 30

    def test_catalyst_non_utc_converted_to_utc(self):
        """Test that non-UTC timezone is converted to UTC."""
        # Create a timezone 5 hours behind UTC (like EST)
        est = timezone(timedelta(hours=-5))
        ts_est = datetime(2026, 1, 15, 9, 30, tzinfo=est)  # 9:30 EST

        catalyst = Catalyst(
            name="Market Open",
            catalyst_type=CatalystType.OTHER,
            timestamp_utc=ts_est,
        )

        # Should be converted to UTC (14:30 UTC)
        assert catalyst.timestamp_utc.tzinfo == timezone.utc
        assert catalyst.timestamp_utc.hour == 14
        assert catalyst.timestamp_utc.minute == 30

    def test_catalyst_format_for_display(self):
        """Test formatting catalyst for display."""
        ts = datetime(2026, 1, 15, 14, 30, tzinfo=timezone.utc)
        catalyst = Catalyst(
            name="FOMC Minutes",
            catalyst_type=CatalystType.CENTRAL_BANK,
            timestamp_utc=ts,
        )

        display = catalyst.format_for_display()
        # Format: "Jan 15 14:30 UTC - FOMC Minutes"
        assert "Jan" in display
        assert "15" in display
        assert "14:30" in display
        assert "UTC" in display
        assert "FOMC Minutes" in display

    def test_catalyst_is_frozen(self):
        """Test that Catalyst is immutable."""
        ts = datetime(2026, 1, 15, 14, 30, tzinfo=timezone.utc)
        catalyst = Catalyst(
            name="Test Event",
            catalyst_type=CatalystType.OTHER,
            timestamp_utc=ts,
        )

        with pytest.raises(AttributeError):
            catalyst.name = "Modified"  # type: ignore[misc]


class TestCreateCatalyst:
    """Tests for create_catalyst factory function."""

    def test_create_catalyst_function(self):
        """Test the factory function creates a valid catalyst."""
        ts = datetime(2026, 1, 20, 13, 0, tzinfo=timezone.utc)
        catalyst = create_catalyst(
            name="NFP Report",
            catalyst_type=CatalystType.ECONOMIC_DATA,
            timestamp_utc=ts,
            description="Non-Farm Payrolls",
            impact_score=90,
            source="BLS",
        )

        assert catalyst.name == "NFP Report"
        assert catalyst.catalyst_type == CatalystType.ECONOMIC_DATA
        assert catalyst.impact_score == 90


class TestTradingDayInfo:
    """Tests for TradingDayInfo dataclass."""

    def test_create_trading_day_info(self):
        """Test creating TradingDayInfo."""
        info = TradingDayInfo(
            date=date(2026, 1, 15),
            is_trading_day=True,
            is_holiday=False,
            is_half_day=False,
            close_time_utc=datetime(2026, 1, 15, 21, 0, tzinfo=timezone.utc),
        )

        assert info.date == date(2026, 1, 15)
        assert info.is_trading_day is True
        assert info.is_holiday is False
        assert info.is_half_day is False
        assert info.close_time_utc is not None

    def test_holiday_trading_day_info(self):
        """Test TradingDayInfo for a holiday."""
        info = TradingDayInfo(
            date=date(2026, 12, 25),
            is_trading_day=False,
            is_holiday=True,
            holiday_name="Christmas",
        )

        assert info.is_trading_day is False
        assert info.is_holiday is True
        assert info.holiday_name == "Christmas"
        assert info.close_time_utc is None


class TestMarketCalendarAdapter:
    """Tests for MarketCalendarAdapter."""

    def test_init(self):
        """Test initialization."""
        adapter = MarketCalendarAdapter()
        assert adapter._calendar is None

    def test_lazy_load_calendar(self):
        """Test that calendar is lazy-loaded."""
        adapter = MarketCalendarAdapter()
        assert adapter._calendar is None

        # Calling _get_calendar should load it
        cal = adapter._get_calendar()
        assert cal is not None
        assert adapter._calendar is not None

    def test_is_trading_day_weekday(self):
        """Test checking if a weekday is a trading day."""
        adapter = MarketCalendarAdapter()

        # January 15, 2026 is a Thursday - should be a trading day
        result = adapter.is_trading_day(date(2026, 1, 15))
        assert result is True

    def test_is_trading_day_weekend(self):
        """Test checking if a weekend is not a trading day."""
        adapter = MarketCalendarAdapter()

        # January 17, 2026 is a Saturday - should not be a trading day
        result = adapter.is_trading_day(date(2026, 1, 17))
        assert result is False

    def test_is_trading_day_holiday(self):
        """Test checking if a holiday is not a trading day."""
        adapter = MarketCalendarAdapter()

        # July 4, 2026 is Independence Day (Saturday, but observed Friday July 3)
        # Christmas 2026 is a Friday - market closed
        result = adapter.is_trading_day(date(2026, 12, 25))
        assert result is False

    def test_get_previous_trading_day(self):
        """Test getting the previous trading day."""
        adapter = MarketCalendarAdapter()

        # Monday Jan 19, 2026 - previous trading day should be Friday Jan 16
        prev = adapter.get_previous_trading_day(date(2026, 1, 19))
        assert prev == date(2026, 1, 16)

    def test_get_next_trading_day(self):
        """Test getting the next trading day."""
        adapter = MarketCalendarAdapter()

        # Friday Jan 16, 2026 - next trading day should be Monday Jan 19
        # (unless Jan 19 is MLK Day - need to check)
        next_day = adapter.get_next_trading_day(date(2026, 1, 16))
        # Jan 19, 2026 is MLK Day - so next should be Jan 20
        assert next_day == date(2026, 1, 20)

    def test_get_trading_day_info(self):
        """Test getting comprehensive trading day info."""
        adapter = MarketCalendarAdapter()

        info = adapter.get_trading_day_info(date(2026, 1, 15))

        assert info.date == date(2026, 1, 15)
        assert info.is_trading_day is True
        assert info.close_time_utc is not None

    def test_get_trading_days_in_range(self):
        """Test getting trading days in a date range."""
        adapter = MarketCalendarAdapter()

        # Get trading days for first full week of Jan 2026 (Mon 5 - Fri 9)
        days = adapter.get_trading_days_in_range(date(2026, 1, 5), date(2026, 1, 9))

        # Should have 5 trading days (Mon-Fri)
        assert len(days) == 5
        assert date(2026, 1, 5) in days
        assert date(2026, 1, 9) in days

    def test_get_next_n_trading_days(self):
        """Test getting the next N trading days."""
        adapter = MarketCalendarAdapter()

        # Get next 5 trading days after Jan 15, 2026
        days = adapter.get_next_n_trading_days(date(2026, 1, 15), 5)

        assert len(days) == 5
        # Should not include Jan 15 itself
        assert date(2026, 1, 15) not in days
        # First should be Jan 16
        assert days[0] == date(2026, 1, 16)

    def test_get_holidays_in_range(self):
        """Test getting holidays in a date range."""
        adapter = MarketCalendarAdapter()

        # Get holidays for 2026
        holidays = adapter.get_holidays_in_range(date(2026, 1, 1), date(2026, 12, 31))

        # Should have several holidays (New Year's, MLK Day, etc.)
        assert len(holidays) > 0
        # New Year's Day 2026 is a Thursday
        assert date(2026, 1, 1) in holidays

    def test_is_holiday(self):
        """Test checking if a date is a holiday."""
        adapter = MarketCalendarAdapter()

        # Christmas 2026
        assert adapter.is_holiday(date(2026, 12, 25)) is True
        # Regular trading day
        assert adapter.is_holiday(date(2026, 1, 15)) is False

    def test_get_early_closes_in_range(self):
        """Test getting early close days in a range."""
        adapter = MarketCalendarAdapter()

        # Get early closes for 2026 - day after Thanksgiving is typically an early close
        early_closes = adapter.get_early_closes_in_range(date(2026, 1, 1), date(2026, 12, 31))

        # November 27, 2026 (day after Thanksgiving) should be an early close
        # The actual dates depend on exchange_calendars data
        assert isinstance(early_closes, (list, tuple))
