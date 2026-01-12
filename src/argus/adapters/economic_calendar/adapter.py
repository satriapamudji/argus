"""Economic calendar adapter for FactsBundleBuilder.

Provides the main interface for getting upcoming economic events and
managing refresh operations. This is the primary entry point for the
economic calendar feature.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from psycopg2.extensions import connection as Connection

from argus.adapters.economic_calendar.fetcher import refresh_economic_calendar
from argus.adapters.economic_calendar.repository import (
    get_event_count,
    get_last_fetch_time,
    get_upcoming_events,
    is_data_stale,
)
from argus.adapters.economic_calendar.types import EconomicEventRow, RefreshResult
from argus.config import EconomicCalendarConfig
from argus.facts_bundle.types import CalendarEventBundle

logger = logging.getLogger(__name__)


def format_event_display(event: EconomicEventRow) -> str:
    """Format an economic event for display in the message.

    Output format: "Jan 8, 14:30 - Non-Farm Payrolls"

    Args:
        event: Database row for the event.

    Returns:
        Formatted display string.
    """
    # Format: "Jan 8, 14:30 - Event Name" (UTC is indicated in section header)
    ts = event.event_timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    else:
        ts = ts.astimezone(timezone.utc)

    date_str = ts.strftime("%b %d, %H:%M").replace(" 0", " ")
    return f"{date_str} - {event.title}"


def event_row_to_bundle(event: EconomicEventRow) -> CalendarEventBundle:
    """Convert database row to CalendarEventBundle.

    Args:
        event: Database row for the event.

    Returns:
        CalendarEventBundle for the facts bundle.
    """
    return CalendarEventBundle(
        name=event.title,
        timestamp_utc=event.event_timestamp,
        event_type="economic",
        formatted_display=format_event_display(event),
    )


class EconomicCalendarAdapter:
    """Adapter for accessing economic calendar data.

    Provides methods to:
    - Get upcoming events as CalendarEventBundle for the facts bundle
    - Check if data is stale
    - Refresh data from ForexFactory
    - Force refresh regardless of staleness

    Usage:
        adapter = EconomicCalendarAdapter(conn, config.economic_calendar)

        # Auto-refresh if stale, then get events
        events = adapter.get_upcoming_events()

        # Or manually control refresh
        if adapter.is_stale():
            result = adapter.force_refresh()
            if result.success:
                events = adapter.get_upcoming_events(auto_refresh=False)
    """

    def __init__(
        self,
        conn: Connection,
        config: EconomicCalendarConfig,
    ) -> None:
        """Initialize the adapter.

        Args:
            conn: Database connection.
            config: Economic calendar configuration.
        """
        self.conn = conn
        self.config = config
        self._source = "forexfactory"

    def get_upcoming_events(
        self,
        from_time: Optional[datetime] = None,
        auto_refresh: bool = True,
    ) -> list[CalendarEventBundle]:
        """Get upcoming economic events as CalendarEventBundle.

        Args:
            from_time: Start time for events (defaults to now UTC).
            auto_refresh: If True, refresh data if stale before querying.

        Returns:
            List of CalendarEventBundle sorted by timestamp.
        """
        if not self.config.enabled:
            logger.debug("Economic calendar is disabled")
            return []

        # Auto-refresh if stale
        if auto_refresh and self.is_stale():
            logger.info("Economic calendar data is stale, refreshing...")
            result = self.force_refresh()
            if not result.success:
                logger.warning(f"Failed to refresh economic calendar: {result.errors}")
                # Continue with stale data if available

        # Calculate time range
        if from_time is None:
            from_time = datetime.now(timezone.utc)
        elif from_time.tzinfo is None:
            from_time = from_time.replace(tzinfo=timezone.utc)

        to_time = from_time + timedelta(days=self.config.lookahead_days)

        # Query database
        rows = get_upcoming_events(
            conn=self.conn,
            start_time=from_time,
            end_time=to_time,
            countries=self.config.countries,
            impact_filter=self.config.impact_filter,
        )

        logger.debug(
            f"Found {len(rows)} upcoming economic events ({from_time.date()} to {to_time.date()})"
        )

        return [event_row_to_bundle(row) for row in rows]

    def is_stale(self) -> bool:
        """Check if the economic calendar data is stale.

        Returns:
            True if data is stale or doesn't exist.
        """
        return is_data_stale(
            conn=self.conn,
            stale_hours=float(self.config.stale_hours),
            source=self._source,
        )

    def force_refresh(self) -> RefreshResult:
        """Force refresh of economic calendar data.

        Returns:
            RefreshResult with statistics and any errors.
        """
        return refresh_economic_calendar(
            conn=self.conn,
            feed_url=self.config.feed_url,
            countries=self.config.countries,
            impact_filter=self.config.impact_filter,
            source=self._source,
        )

    def refresh_if_stale(self) -> Optional[RefreshResult]:
        """Refresh data only if stale.

        Returns:
            RefreshResult if refresh was performed, None otherwise.
        """
        if self.is_stale():
            return self.force_refresh()
        return None

    def get_last_fetch_time(self) -> Optional[datetime]:
        """Get the last time data was fetched.

        Returns:
            Last fetch timestamp, or None if no data.
        """
        return get_last_fetch_time(self.conn, source=self._source)

    def get_event_count(self) -> int:
        """Get count of events matching config filters.

        Returns:
            Number of events in database.
        """
        return get_event_count(
            conn=self.conn,
            source=self._source,
            countries=self.config.countries,
            impact_filter=self.config.impact_filter,
        )

    def get_status(self) -> dict[str, object]:
        """Get status information for CLI display.

        Returns:
            Dict with status fields: enabled, stale, last_fetch, event_count,
            config summary.
        """
        last_fetch = self.get_last_fetch_time()
        return {
            "enabled": self.config.enabled,
            "stale": self.is_stale(),
            "last_fetch": last_fetch.isoformat() if last_fetch else None,
            "event_count": self.get_event_count(),
            "feed_url": self.config.feed_url,
            "countries": self.config.countries,
            "impact_filter": self.config.impact_filter,
            "lookahead_days": self.config.lookahead_days,
            "stale_hours": self.config.stale_hours,
        }
