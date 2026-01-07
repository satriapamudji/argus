"""HTTP fetcher for ForexFactory economic calendar data.

Fetches JSON from ForexFactory, parses events, converts timestamps to UTC,
and upserts to database via repository.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from argus.adapters.economic_calendar.repository import upsert_economic_events
from argus.adapters.economic_calendar.types import RawEconomicEvent, RefreshResult
from psycopg2.extensions import connection as Connection

logger = logging.getLogger(__name__)

# Default settings
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; ArgusBot/1.0; +https://github.com/argus-news-bot)"


def parse_forexfactory_timestamp(date_str: str) -> Optional[datetime]:
    """Parse ForexFactory timestamp to UTC datetime.

    ForexFactory provides timestamps in ISO 8601 format with timezone.
    Example: "2025-01-08T13:30:00-05:00"

    Args:
        date_str: ISO 8601 timestamp string.

    Returns:
        UTC datetime, or None if parsing fails.
    """
    if not date_str:
        return None

    try:
        # Parse ISO 8601 format with timezone
        dt = datetime.fromisoformat(date_str)
        # Convert to UTC
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError) as e:
        logger.warning(f"Failed to parse timestamp '{date_str}': {e}")
        return None


def parse_forexfactory_event(raw: dict[str, Any]) -> Optional[RawEconomicEvent]:
    """Parse a single ForexFactory event from JSON.

    Expected JSON format:
    {
        "title": "Non-Farm Employment Change",
        "country": "USD",
        "date": "2025-01-10T13:30:00-05:00",
        "impact": "High",
        "forecast": "150K",
        "previous": "227K"
    }

    Args:
        raw: Raw JSON dict from ForexFactory.

    Returns:
        RawEconomicEvent, or None if required fields are missing.
    """
    title = raw.get("title")
    country = raw.get("country")
    date_str = raw.get("date")
    impact = raw.get("impact")

    # Validate required fields - all must be non-None strings
    if not isinstance(title, str) or not title:
        logger.debug(f"Skipping event with missing/invalid title: {raw}")
        return None
    if not isinstance(country, str) or not country:
        logger.debug(f"Skipping event with missing/invalid country: {raw}")
        return None
    if not isinstance(date_str, str) or not date_str:
        logger.debug(f"Skipping event with missing/invalid date: {raw}")
        return None
    if not isinstance(impact, str) or not impact:
        logger.debug(f"Skipping event with missing/invalid impact: {raw}")
        return None

    timestamp = parse_forexfactory_timestamp(date_str)
    if timestamp is None:
        return None

    # Get optional fields with proper type handling
    forecast = raw.get("forecast")
    previous = raw.get("previous")

    return RawEconomicEvent(
        title=title,
        country=country,
        timestamp_utc=timestamp,
        impact=impact,
        forecast=forecast if isinstance(forecast, str) else None,
        previous=previous if isinstance(previous, str) else None,
    )


def fetch_forexfactory_events(
    feed_url: str,
    countries: Optional[list[str]] = None,
    impact_filter: Optional[list[str]] = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[list[RawEconomicEvent], Optional[str]]:
    """Fetch and parse events from ForexFactory JSON feed.

    Args:
        feed_url: URL of the ForexFactory JSON feed.
        countries: Optional list of country codes to filter (e.g., ["USD"]).
        impact_filter: Optional list of impact levels to filter (e.g., ["High"]).
        timeout_seconds: HTTP request timeout.

    Returns:
        Tuple of (list of parsed events, error message or None).
    """
    try:
        with httpx.Client(
            timeout=httpx.Timeout(timeout_seconds),
            headers={"User-Agent": DEFAULT_USER_AGENT},
            follow_redirects=True,
        ) as client:
            response = client.get(feed_url)
            response.raise_for_status()

            data = response.json()

            if not isinstance(data, list):
                return [], f"Expected list, got {type(data).__name__}"

            events: list[RawEconomicEvent] = []
            for item in data:
                event = parse_forexfactory_event(item)
                if event is None:
                    continue

                # Filter by country if specified
                if countries and event.country not in countries:
                    continue

                # Filter by impact if specified
                if impact_filter and event.impact not in impact_filter:
                    continue

                events.append(event)

            logger.info(
                f"Fetched {len(events)} events from ForexFactory (filtered from {len(data)} total)"
            )
            return events, None

    except httpx.TimeoutException:
        error = f"Timeout fetching {feed_url}"
        logger.error(error)
        return [], error

    except httpx.HTTPStatusError as e:
        error = f"HTTP {e.response.status_code} from {feed_url}"
        logger.error(error)
        return [], error

    except httpx.HTTPError as e:
        error = f"HTTP error fetching {feed_url}: {e}"
        logger.error(error)
        return [], error

    except Exception as e:
        error = f"Unexpected error fetching {feed_url}: {e}"
        logger.exception(error)
        return [], error


def refresh_economic_calendar(
    conn: Connection,
    feed_url: str,
    countries: Optional[list[str]] = None,
    impact_filter: Optional[list[str]] = None,
    source: str = "forexfactory",
) -> RefreshResult:
    """Fetch events from ForexFactory and upsert to database.

    This is the main entry point for refreshing the economic calendar.

    Args:
        conn: Database connection.
        feed_url: URL of the ForexFactory JSON feed.
        countries: Optional list of country codes to filter.
        impact_filter: Optional list of impact levels to filter.
        source: Data source identifier.

    Returns:
        RefreshResult with fetch/upsert statistics.
    """
    start_time = time.monotonic()
    fetched_at = datetime.now(timezone.utc)

    # Fetch events
    events, error = fetch_forexfactory_events(
        feed_url=feed_url,
        countries=countries,
        impact_filter=impact_filter,
    )

    if error:
        duration = time.monotonic() - start_time
        return RefreshResult(
            events_fetched=0,
            events_inserted=0,
            events_updated=0,
            source=source,
            fetched_at=fetched_at,
            duration_seconds=duration,
            errors=[error],
        )

    # Upsert to database
    try:
        inserted, updated = upsert_economic_events(conn, events, source=source)
    except Exception as e:
        duration = time.monotonic() - start_time
        error_msg = f"Database error during upsert: {e}"
        logger.exception(error_msg)
        return RefreshResult(
            events_fetched=len(events),
            events_inserted=0,
            events_updated=0,
            source=source,
            fetched_at=fetched_at,
            duration_seconds=duration,
            errors=[error_msg],
        )

    duration = time.monotonic() - start_time
    logger.info(
        f"Economic calendar refresh complete: "
        f"{len(events)} fetched, {inserted} inserted, {updated} updated "
        f"in {duration:.2f}s"
    )

    return RefreshResult(
        events_fetched=len(events),
        events_inserted=inserted,
        events_updated=updated,
        source=source,
        fetched_at=fetched_at,
        duration_seconds=duration,
    )
