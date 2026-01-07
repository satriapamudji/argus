"""Market calendar adapter for NYSE trading calendar.

Provides trading day information, holidays, half-days/early closes,
and upcoming catalyst events with UTC timezone labeling.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Optional, Sequence
import logging

logger = logging.getLogger(__name__)


class CatalystType(Enum):
    """Type of market catalyst event."""

    CENTRAL_BANK = "central_bank"
    ECONOMIC_DATA = "economic_data"
    EARNINGS = "earnings"
    POLITICAL = "political"
    AUCTION = "auction"
    HOLIDAY = "holiday"
    HALF_DAY = "half_day"
    OTHER = "other"


@dataclass(frozen=True)
class Catalyst:
    """A market catalyst event with UTC timezone labeling.

    All timestamps are explicitly in UTC for the *Key Dates (UTC)* section.

    Attributes:
        name: Short descriptive name of the event.
        catalyst_type: Type categorization of the event.
        timestamp_utc: Event time in UTC (required for display).
        description: Optional longer description.
        impact_score: Optional 0-100 score indicating expected market impact.
        source: Optional source of the catalyst information.
    """

    name: str
    catalyst_type: CatalystType
    timestamp_utc: datetime
    description: Optional[str] = None
    impact_score: Optional[int] = None
    source: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate that timestamp is UTC."""
        if self.timestamp_utc.tzinfo is None:
            # Convert naive datetime to UTC
            object.__setattr__(
                self,
                "timestamp_utc",
                self.timestamp_utc.replace(tzinfo=timezone.utc),
            )
        elif self.timestamp_utc.tzinfo != timezone.utc:
            # Convert to UTC
            object.__setattr__(
                self,
                "timestamp_utc",
                self.timestamp_utc.astimezone(timezone.utc),
            )

    def format_for_display(self) -> str:
        """Format the catalyst for the Key Dates section.

        Returns:
            Formatted string like "Jan 8 14:30 UTC - FOMC Minutes"
        """
        # Use %d instead of %-d for cross-platform compatibility
        day = self.timestamp_utc.day
        dt_str = self.timestamp_utc.strftime(f"%b {day} %H:%M UTC")
        return f"{dt_str} - {self.name}"


@dataclass
class TradingDayInfo:
    """Information about a specific trading day.

    Attributes:
        date: The date in question.
        is_trading_day: Whether the market is open.
        is_holiday: Whether this is a market holiday.
        is_half_day: Whether this is an early close day.
        holiday_name: Name of the holiday if applicable.
        close_time_utc: Market close time in UTC (if trading day).
    """

    date: date
    is_trading_day: bool
    is_holiday: bool = False
    is_half_day: bool = False
    holiday_name: Optional[str] = None
    close_time_utc: Optional[datetime] = None


@dataclass
class MarketCalendarAdapter:
    """Adapter for NYSE market calendar operations.

    Provides trading day lookups, holiday information, and early close detection.
    Uses exchange_calendars library for accurate NYSE calendar data.
    """

    _calendar: Any = field(default=None, repr=False)

    def _get_calendar(self) -> Any:
        """Lazy-load the NYSE calendar.

        Returns:
            exchange_calendars calendar object for NYSE.

        Raises:
            ImportError: If exchange_calendars is not installed.
        """
        if self._calendar is None:
            try:
                import exchange_calendars as xcals

                self._calendar = xcals.get_calendar("XNYS")
            except ImportError as e:
                raise ImportError(
                    "exchange_calendars is required for market calendar. "
                    "Install with: pip install exchange_calendars"
                ) from e
        return self._calendar

    def is_trading_day(self, dt: date) -> bool:
        """Check if a date is a trading day.

        Args:
            dt: The date to check.

        Returns:
            True if the NYSE is open on this date.
        """
        cal = self._get_calendar()
        try:
            return bool(cal.is_session(dt.isoformat()))
        except Exception:
            return False

    def is_holiday(self, dt: date) -> bool:
        """Check if a date is a market holiday.

        A holiday is a weekday (Mon-Fri) that is not a trading day.

        Args:
            dt: The date to check.

        Returns:
            True if this is a market holiday.
        """
        # A holiday is a weekday that's not a trading session
        if dt.weekday() >= 5:  # Saturday or Sunday
            return False
        return not self.is_trading_day(dt)

    def is_early_close(self, dt: date) -> bool:
        """Check if a date is an early close / half day.

        Args:
            dt: The date to check.

        Returns:
            True if this is an early close day.
        """
        cal = self._get_calendar()
        try:
            import pandas as pd

            early_closes = cal.early_closes
            return pd.Timestamp(dt) in early_closes
        except Exception:
            return False

    def get_trading_day_info(self, dt: date) -> TradingDayInfo:
        """Get comprehensive trading day information.

        Args:
            dt: The date to get info for.

        Returns:
            TradingDayInfo with all relevant details.
        """
        is_trading = self.is_trading_day(dt)
        is_holiday = self.is_holiday(dt)
        is_half = self.is_early_close(dt) if is_trading else False

        # Determine close time (in UTC)
        close_time_utc = None
        if is_trading:
            if is_half:
                # NYSE early close is 1:00 PM ET = 18:00 UTC (or 17:00 during DST)
                # Using approximate UTC time; actual varies with DST
                close_time_utc = datetime(dt.year, dt.month, dt.day, 18, 0, tzinfo=timezone.utc)
            else:
                # NYSE regular close is 4:00 PM ET = 21:00 UTC (or 20:00 during DST)
                close_time_utc = datetime(dt.year, dt.month, dt.day, 21, 0, tzinfo=timezone.utc)

        return TradingDayInfo(
            date=dt,
            is_trading_day=is_trading,
            is_holiday=is_holiday,
            is_half_day=is_half,
            holiday_name=None,  # Could be enhanced to get holiday name
            close_time_utc=close_time_utc,
        )

    def get_previous_trading_day(self, dt: date) -> date:
        """Get the most recent trading day before the given date.

        Args:
            dt: The reference date.

        Returns:
            The previous trading day.
        """
        cal = self._get_calendar()
        try:
            prev_session = cal.previous_session(dt.isoformat())
            return prev_session.date()  # type: ignore[no-any-return]
        except Exception as e:
            logger.warning(f"Failed to get previous trading day: {e}")
            # Fallback: simple backward search
            from datetime import timedelta

            check_date = dt - timedelta(days=1)
            for _ in range(10):
                if self.is_trading_day(check_date):
                    return check_date
                check_date -= timedelta(days=1)
            return dt - timedelta(days=1)

    def get_next_trading_day(self, dt: date) -> date:
        """Get the next trading day after the given date.

        Args:
            dt: The reference date.

        Returns:
            The next trading day.
        """
        cal = self._get_calendar()
        try:
            next_session = cal.next_session(dt.isoformat())
            return next_session.date()  # type: ignore[no-any-return]
        except Exception as e:
            logger.warning(f"Failed to get next trading day: {e}")
            # Fallback: simple forward search
            from datetime import timedelta

            check_date = dt + timedelta(days=1)
            for _ in range(10):
                if self.is_trading_day(check_date):
                    return check_date
                check_date += timedelta(days=1)
            return dt + timedelta(days=1)

    def get_trading_days_in_range(self, start: date, end: date) -> Sequence[date]:
        """Get all trading days in a date range (inclusive).

        Args:
            start: Start date (inclusive).
            end: End date (inclusive).

        Returns:
            Sequence of trading dates.
        """
        cal = self._get_calendar()
        try:
            sessions = cal.sessions_in_range(start.isoformat(), end.isoformat())
            return [s.date() for s in sessions]
        except Exception as e:
            logger.warning(f"Failed to get trading days in range: {e}")
            # Fallback
            from datetime import timedelta

            result = []
            current = start
            while current <= end:
                if self.is_trading_day(current):
                    result.append(current)
                current += timedelta(days=1)
            return result

    def get_next_n_trading_days(self, dt: date, n: int) -> Sequence[date]:
        """Get the next N trading days starting from a date.

        Args:
            dt: Starting date (not included in result).
            n: Number of trading days to return.

        Returns:
            Sequence of N trading dates.
        """
        result: list[date] = []
        current = dt
        while len(result) < n:
            current = self.get_next_trading_day(current)
            result.append(current)
        return result

    def get_holidays_in_range(self, start: date, end: date) -> Sequence[date]:
        """Get all market holidays in a date range.

        A holiday is a weekday that is not a trading session.

        Args:
            start: Start date (inclusive).
            end: End date (inclusive).

        Returns:
            Sequence of holiday dates.
        """
        from datetime import timedelta

        result: list[date] = []
        current = start
        while current <= end:
            if self.is_holiday(current):
                result.append(current)
            current += timedelta(days=1)
        return result

    def get_early_closes_in_range(self, start: date, end: date) -> Sequence[date]:
        """Get all early close days in a date range.

        Args:
            start: Start date (inclusive).
            end: End date (inclusive).

        Returns:
            Sequence of early close dates.
        """
        cal = self._get_calendar()
        try:
            import pandas as pd

            early_closes = cal.early_closes
            start_ts = pd.Timestamp(start)
            end_ts = pd.Timestamp(end)
            filtered = early_closes[(early_closes >= start_ts) & (early_closes <= end_ts)]
            return [ec.date() for ec in filtered]
        except Exception as e:
            logger.warning(f"Failed to get early closes: {e}")
            return []


def create_catalyst(
    name: str,
    catalyst_type: CatalystType,
    timestamp_utc: datetime,
    description: Optional[str] = None,
    impact_score: Optional[int] = None,
    source: Optional[str] = None,
) -> Catalyst:
    """Factory function to create a Catalyst with proper UTC handling.

    Args:
        name: Short descriptive name.
        catalyst_type: Type of catalyst.
        timestamp_utc: Event time (will be converted to UTC if needed).
        description: Optional description.
        impact_score: Optional impact score (0-100).
        source: Optional source.

    Returns:
        Catalyst instance with UTC timestamp.
    """
    return Catalyst(
        name=name,
        catalyst_type=catalyst_type,
        timestamp_utc=timestamp_utc,
        description=description,
        impact_score=impact_score,
        source=source,
    )
