"""Window selection logic for run orchestrator.

Handles DST-safe timezone conversions for selecting news windows
based on run mode and schedule.
"""

from datetime import date, datetime, time, timedelta
from typing import Optional
import logging

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore[import-not-found,no-redef,unused-ignore]

from argus.orchestrator.types import RunMode, WindowConfig
from argus.adapters.calendar import MarketCalendarAdapter

logger = logging.getLogger(__name__)

# Timezone definitions
TZ_NEW_YORK = ZoneInfo("America/New_York")
TZ_SINGAPORE = ZoneInfo("Asia/Singapore")
TZ_UTC = ZoneInfo("UTC")

# Window durations per mode (in hours)
WINDOW_HOURS = {
    RunMode.US_CLOSE: 24,  # Last 24h of news
    RunMode.WEEKEND_WRAP: 120,  # Mon-Fri (~5 days)
    RunMode.MONDAY_PREVIEW: 120,  # Full prior week's news for context
}


def get_ny_market_close(trading_date: date) -> datetime:
    """Get NYSE market close time for a given trading date.

    Regular close is 4:00 PM ET. Early close is 1:00 PM ET.
    Returns timezone-aware datetime in America/New_York.

    Args:
        trading_date: The trading date.

    Returns:
        Datetime of market close in NY timezone.
    """
    # Regular close is 4:00 PM ET (16:00)
    close_time = time(16, 0, 0)
    return datetime.combine(trading_date, close_time, tzinfo=TZ_NEW_YORK)


def get_ny_market_open(trading_date: date) -> datetime:
    """Get NYSE market open time for a given trading date.

    Regular open is 9:30 AM ET.
    Returns timezone-aware datetime in America/New_York.

    Args:
        trading_date: The trading date.

    Returns:
        Datetime of market open in NY timezone.
    """
    open_time = time(9, 30, 0)
    return datetime.combine(trading_date, open_time, tzinfo=TZ_NEW_YORK)


def get_previous_friday_close(reference_date: date) -> datetime:
    """Get the previous Friday's market close.

    Used for weekend_wrap to determine the end of the trading week.

    Args:
        reference_date: Reference date (typically Saturday).

    Returns:
        Friday's market close datetime in NY timezone.
    """
    days_since_friday = (reference_date.weekday() - 4) % 7
    if days_since_friday == 0 and reference_date.weekday() != 4:
        days_since_friday = 7
    friday = reference_date - timedelta(days=days_since_friday)
    return get_ny_market_close(friday)


def get_previous_monday_open(reference_date: date) -> datetime:
    """Get the previous Monday's market open.

    Used for weekend_wrap to determine the start of the trading week.

    Args:
        reference_date: Reference date (typically Saturday).

    Returns:
        Monday's market open datetime in NY timezone.
    """
    days_since_monday = (reference_date.weekday() - 0) % 7
    if days_since_monday == 0 and reference_date.weekday() != 0:
        days_since_monday = 7
    monday = reference_date - timedelta(days=days_since_monday)
    return get_ny_market_open(monday)


def get_window_for_us_close(now: datetime) -> WindowConfig:
    """Calculate window for us_close run.

    The us_close run covers the prior US cash session close plus
    the last ~18-24h of relevant news.

    Schedule: Tue-Fri 06:00 SGT

    Args:
        now: Current datetime (timezone-aware).

    Returns:
        WindowConfig for the us_close run.
    """
    # Convert to NY time to find the trading session
    _ = now.astimezone(TZ_NEW_YORK)  # Available for future use if needed

    # For us_close at 06:00 SGT, the prior US session closed
    # approximately 12-18 hours ago (4:00 PM ET previous day)
    # We look back 24 hours from now
    window_hours = WINDOW_HOURS[RunMode.US_CLOSE]
    window_start = now - timedelta(hours=window_hours)
    window_end = now

    logger.debug(f"us_close window: {window_start.isoformat()} to {window_end.isoformat()}")

    return WindowConfig(
        start=window_start,
        end=window_end,
        window_hours=window_hours,
        mode=RunMode.US_CLOSE,
    )


def get_window_for_weekend_wrap(now: datetime) -> WindowConfig:
    """Calculate window for weekend_wrap run.

    The weekend_wrap covers Monday open → Friday close (NY time)
    plus weekend pre-read catalysts.

    Schedule: Sat 10:00 SGT

    Args:
        now: Current datetime (timezone-aware).

    Returns:
        WindowConfig for the weekend_wrap run.
    """
    now_ny = now.astimezone(TZ_NEW_YORK)
    today = now_ny.date()

    # Find the trading week that just ended
    _ = get_previous_friday_close(today)  # Kept for reference; window extends to now
    monday_open = get_previous_monday_open(today)

    # Window is Monday open to now (to include weekend catalysts)
    window_hours = WINDOW_HOURS[RunMode.WEEKEND_WRAP]

    logger.debug(f"weekend_wrap window: {monday_open.isoformat()} to {now.isoformat()}")

    return WindowConfig(
        start=monday_open,
        end=now,
        window_hours=window_hours,
        mode=RunMode.WEEKEND_WRAP,
    )


def get_window_for_monday_preview(now: datetime) -> WindowConfig:
    """Calculate window for monday_preview run.

    The monday_preview looks back 72h for headline_score calculation.

    Schedule: Sun 18:10 America/New_York

    Args:
        now: Current datetime (timezone-aware).

    Returns:
        WindowConfig for the monday_preview run.
    """
    window_hours = WINDOW_HOURS[RunMode.MONDAY_PREVIEW]
    window_start = now - timedelta(hours=window_hours)
    window_end = now

    logger.debug(f"monday_preview window: {window_start.isoformat()} to {window_end.isoformat()}")

    return WindowConfig(
        start=window_start,
        end=window_end,
        window_hours=window_hours,
        mode=RunMode.MONDAY_PREVIEW,
    )


def get_window_for_mode(
    mode: RunMode,
    now: Optional[datetime] = None,
) -> WindowConfig:
    """Get the appropriate window configuration for a run mode.

    Args:
        mode: The run mode.
        now: Current datetime (defaults to now in UTC).

    Returns:
        WindowConfig for the specified mode.

    Raises:
        ValueError: If mode is not recognized.
    """
    if now is None:
        now = datetime.now(TZ_UTC)

    # Ensure timezone-aware
    if now.tzinfo is None:
        now = now.replace(tzinfo=TZ_UTC)

    if mode == RunMode.US_CLOSE:
        return get_window_for_us_close(now)
    elif mode == RunMode.WEEKEND_WRAP:
        return get_window_for_weekend_wrap(now)
    elif mode == RunMode.MONDAY_PREVIEW:
        return get_window_for_monday_preview(now)
    else:
        raise ValueError(f"Unknown run mode: {mode}")


def get_trading_date_for_run(
    mode: RunMode,
    now: Optional[datetime] = None,
) -> date:
    """Determine the trading date for a run.

    For us_close: The previous US trading session.
    For weekend_wrap: Friday's date.
    For monday_preview: The upcoming Monday.

    Args:
        mode: The run mode.
        now: Current datetime (defaults to now in UTC).

    Returns:
        The trading date associated with this run.
    """
    if now is None:
        now = datetime.now(TZ_UTC)

    if now.tzinfo is None:
        now = now.replace(tzinfo=TZ_UTC)

    now_ny = now.astimezone(TZ_NEW_YORK)
    today_ny = now_ny.date()

    if mode == RunMode.US_CLOSE:
        # The trading date is always the most recent NYSE trading day.
        #
        # - If today is not a trading day (weekend/holiday), roll back to the last session.
        # - If today is a trading day but the cash session hasn't closed yet, use the
        #   previous trading day (e.g., Monday morning -> prior Friday).
        calendar = MarketCalendarAdapter()

        if not calendar.is_trading_day(today_ny):
            return calendar.get_previous_trading_day(today_ny)

        day_info = calendar.get_trading_day_info(today_ny)
        close_time_local = time(13, 0, 0) if day_info.is_half_day else time(16, 0, 0)
        close_dt_ny = datetime.combine(today_ny, close_time_local, tzinfo=TZ_NEW_YORK)

        if now_ny >= close_dt_ny:
            return today_ny

        return calendar.get_previous_trading_day(today_ny)

    elif mode == RunMode.WEEKEND_WRAP:
        # The trading date is Friday
        return get_previous_friday_close(today_ny).date()

    elif mode == RunMode.MONDAY_PREVIEW:
        # The trading date is the upcoming Monday
        days_until_monday = (7 - today_ny.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7  # If today is Monday, next Monday
        # Actually, if it's Sunday, Monday is tomorrow
        if today_ny.weekday() == 6:  # Sunday
            return today_ny + timedelta(days=1)
        return today_ny + timedelta(days=days_until_monday)

    else:
        raise ValueError(f"Unknown run mode: {mode}")
