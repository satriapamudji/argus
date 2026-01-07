"""Holiday and half-day behavior handler for run orchestrator.

Handles the behavior when a run falls on a market holiday or early close day,
applying the configured HolidayBehavior or HalfDayBehavior.
"""

from datetime import date
from typing import Optional
import logging

from argus.adapters.calendar import MarketCalendarAdapter
from argus.orchestrator.types import (
    HalfDayBehavior,
    HolidayBehavior,
    HolidayInfo,
    RunMode,
)

logger = logging.getLogger(__name__)

# Default behaviors per mode
DEFAULT_HOLIDAY_BEHAVIORS: dict[RunMode, HolidayBehavior] = {
    RunMode.US_CLOSE: HolidayBehavior.PUBLISH_CLOSED_NOTE,
    RunMode.WEEKEND_WRAP: HolidayBehavior.SKIP,  # Not applicable
    RunMode.MONDAY_PREVIEW: HolidayBehavior.PUBLISH_CLOSED_NOTE,
}

DEFAULT_HALF_DAY_BEHAVIORS: dict[RunMode, HalfDayBehavior] = {
    RunMode.US_CLOSE: HalfDayBehavior.LABEL_HALF_DAY,
    RunMode.WEEKEND_WRAP: HalfDayBehavior.LABEL_HALF_DAY,
    RunMode.MONDAY_PREVIEW: HalfDayBehavior.LABEL_HALF_DAY,
}


def check_holiday_status(
    trading_date: date,
    mode: RunMode,
    calendar: Optional[MarketCalendarAdapter] = None,
    holiday_behavior: Optional[HolidayBehavior] = None,
    half_day_behavior: Optional[HalfDayBehavior] = None,
) -> HolidayInfo:
    """Check and apply holiday/half-day behavior for a run.

    Args:
        trading_date: The trading date to check.
        mode: The run mode.
        calendar: Optional calendar adapter (creates one if not provided).
        holiday_behavior: Override for holiday behavior.
        half_day_behavior: Override for half-day behavior.

    Returns:
        HolidayInfo with status and applied behavior.
    """
    if calendar is None:
        calendar = MarketCalendarAdapter()

    # Use configured or default behaviors
    h_behavior = holiday_behavior or DEFAULT_HOLIDAY_BEHAVIORS.get(
        mode, HolidayBehavior.PUBLISH_CLOSED_NOTE
    )
    hd_behavior = half_day_behavior or DEFAULT_HALF_DAY_BEHAVIORS.get(
        mode, HalfDayBehavior.LABEL_HALF_DAY
    )

    # Get trading day info
    day_info = calendar.get_trading_day_info(trading_date)

    # Build result
    result = HolidayInfo(
        is_holiday=day_info.is_holiday,
        is_half_day=day_info.is_half_day,
        holiday_name=day_info.holiday_name,
    )

    # Handle holiday
    if day_info.is_holiday:
        logger.info(f"Trading date {trading_date} is a market holiday")
        result.behavior_applied = h_behavior.value

        if h_behavior == HolidayBehavior.SKIP:
            result.should_skip = True
            logger.info("Holiday behavior: SKIP - run will be skipped")
        elif h_behavior == HolidayBehavior.PUBLISH_CLOSED_NOTE:
            result.should_skip = False
            result.label_text = _get_holiday_label(day_info.holiday_name)
            logger.info(f"Holiday behavior: PUBLISH_CLOSED_NOTE - label: {result.label_text}")

        return result

    # Handle half-day / early close
    if day_info.is_half_day:
        logger.info(f"Trading date {trading_date} is an early close day")
        result.behavior_applied = hd_behavior.value

        if hd_behavior == HalfDayBehavior.SKIP:
            result.should_skip = True
            logger.info("Half-day behavior: SKIP - run will be skipped")
        elif hd_behavior == HalfDayBehavior.LABEL_HALF_DAY:
            result.should_skip = False
            result.label_text = "🕐 Early Close Day"
            logger.info("Half-day behavior: LABEL_HALF_DAY")

        return result

    # Normal trading day
    logger.debug(f"Trading date {trading_date} is a normal trading day")
    return result


def _get_holiday_label(holiday_name: Optional[str]) -> str:
    """Generate the holiday label text.

    Args:
        holiday_name: Name of the holiday (may be None).

    Returns:
        Formatted holiday label.
    """
    if holiday_name:
        return f"🚫 Markets Closed ({holiday_name})"
    return "🚫 Markets Closed"


def get_next_trading_date_for_run(
    trading_date: date,
    mode: RunMode,
    calendar: Optional[MarketCalendarAdapter] = None,
) -> date:
    """Get the next valid trading date for a run.

    Useful when a run should be rescheduled due to holiday skip.

    Args:
        trading_date: The original trading date.
        mode: The run mode.
        calendar: Optional calendar adapter.

    Returns:
        The next valid trading date.
    """
    if calendar is None:
        calendar = MarketCalendarAdapter()

    # For weekend_wrap, we want the next Friday
    if mode == RunMode.WEEKEND_WRAP:
        # Find next week's Friday
        next_trading = calendar.get_next_trading_day(trading_date)
        # Keep going until we hit a Friday
        while next_trading.weekday() != 4:  # 4 = Friday
            next_trading = calendar.get_next_trading_day(next_trading)
        return next_trading

    # For other modes, just get next trading day
    return calendar.get_next_trading_day(trading_date)


def should_run_monday_preview(
    preview_date: date,
    calendar: Optional[MarketCalendarAdapter] = None,
) -> tuple[bool, str]:
    """Determine if monday_preview should run for a given Monday.

    Checks if the Monday (or next trading day) is worth previewing.
    May skip if entire week is holidays.

    Args:
        preview_date: The Monday to preview.
        calendar: Optional calendar adapter.

    Returns:
        Tuple of (should_run, reason).
    """
    if calendar is None:
        calendar = MarketCalendarAdapter()

    # Get trading days for the week
    from datetime import timedelta

    week_start = preview_date
    week_end = preview_date + timedelta(days=4)  # Mon-Fri

    trading_days = calendar.get_trading_days_in_range(week_start, week_end)

    if not trading_days:
        return False, "No trading days in the upcoming week"

    if len(trading_days) < 3:
        return True, f"Short week: only {len(trading_days)} trading days"

    return True, f"Normal week: {len(trading_days)} trading days"
