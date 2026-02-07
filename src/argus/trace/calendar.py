"""DB-free economic calendar conversion for trace module.

Converts RawEconomicEvent (from fetch) to CalendarEventBundle without
requiring database access.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from argus.adapters.economic_calendar.fetcher import fetch_forexfactory_events
from argus.adapters.economic_calendar.types import RawEconomicEvent
from argus.config import EconomicCalendarConfig
from argus.facts_bundle.types import CalendarEventBundle

logger = logging.getLogger(__name__)


def format_raw_event_display(event: RawEconomicEvent) -> str:
    """Format a raw economic event for display in the message.

    Output format: "Jan 8, 14:30 - Non-Farm Payrolls"

    Args:
        event: Raw event from ForexFactory fetch.

    Returns:
        Formatted display string.
    """
    # Ensure UTC
    ts = event.timestamp_utc
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    else:
        ts = ts.astimezone(timezone.utc)

    # Format: "Jan 8, 14:30 - Event Name"
    date_str = ts.strftime("%b %d, %H:%M").replace(" 0", " ")
    return f"{date_str} - {event.title}"


def raw_event_to_bundle(event: RawEconomicEvent) -> CalendarEventBundle:
    """Convert raw fetched event to CalendarEventBundle.

    This is the DB-free equivalent of adapter.event_row_to_bundle().

    Args:
        event: Raw event from ForexFactory fetch.

    Returns:
        CalendarEventBundle for the facts bundle.
    """
    return CalendarEventBundle(
        name=event.title,
        timestamp_utc=event.timestamp_utc,
        event_type="economic",
        formatted_display=format_raw_event_display(event),
    )


def fetch_upcoming_events(
    config: EconomicCalendarConfig,
    from_time: Optional[datetime] = None,
) -> list[CalendarEventBundle]:
    """Fetch upcoming economic events directly (no DB).

    This is the DB-free equivalent of EconomicCalendarAdapter.get_upcoming_events().

    Args:
        config: Economic calendar configuration.
        from_time: Start time for events (defaults to now UTC).

    Returns:
        List of CalendarEventBundle sorted by timestamp.
    """
    if not config.enabled:
        logger.debug("Economic calendar is disabled")
        return []

    # Calculate time range
    if from_time is None:
        from_time = datetime.now(timezone.utc)
    elif from_time.tzinfo is None:
        from_time = from_time.replace(tzinfo=timezone.utc)

    to_time = from_time + timedelta(days=config.lookahead_days)

    # Fetch directly from ForexFactory
    try:
        raw_events, error = fetch_forexfactory_events(
            feed_url=config.feed_url,
            countries=config.countries,
            impact_filter=config.impact_filter,
        )
        if error:
            logger.error(f"Failed to fetch economic calendar: {error}")
            return []
    except Exception as e:
        logger.error(f"Failed to fetch economic calendar: {e}")
        return []

    # Filter to time range
    filtered_events: list[RawEconomicEvent] = [
        event for event in raw_events if from_time <= event.timestamp_utc <= to_time
    ]

    # Sort by timestamp
    filtered_events.sort(key=lambda e: e.timestamp_utc)

    logger.debug(
        f"Fetched {len(filtered_events)} upcoming economic events "
        f"({from_time.date()} to {to_time.date()})"
    )

    return [raw_event_to_bundle(event) for event in filtered_events]
