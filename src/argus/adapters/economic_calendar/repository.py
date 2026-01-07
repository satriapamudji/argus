"""Repository layer for economic calendar database operations.

Follows the codebase pattern of raw SQL with psycopg2, returning typed dataclasses.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from psycopg2.extensions import connection as Connection

from argus.adapters.economic_calendar.types import (
    EconomicEventRow,
    RawEconomicEvent,
)


def upsert_economic_events(
    conn: Connection,
    events: list[RawEconomicEvent],
    source: str = "forexfactory",
) -> tuple[int, int]:
    """Upsert economic events into the database.

    Uses ON CONFLICT to update existing events (by title, timestamp, source, country).
    Updates forecast/previous/actual values if they change.

    Args:
        conn: Database connection.
        events: List of parsed economic events.
        source: Data source identifier.

    Returns:
        Tuple of (inserted_count, updated_count).
    """
    if not events:
        return 0, 0

    inserted = 0
    updated = 0

    with conn.cursor() as cur:
        for event in events:
            # Use INSERT ... ON CONFLICT DO UPDATE
            # xmax = 0 means row was inserted, otherwise updated
            cur.execute(
                """
                INSERT INTO economic_calendar_events 
                    (title, country, event_timestamp, impact, forecast, previous, source, fetched_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (title, event_timestamp, source, country) 
                DO UPDATE SET
                    forecast = EXCLUDED.forecast,
                    previous = EXCLUDED.previous,
                    fetched_at = NOW()
                RETURNING (xmax = 0) AS inserted
                """,
                (
                    event.title,
                    event.country,
                    event.timestamp_utc,
                    event.impact,
                    event.forecast,
                    event.previous,
                    source,
                ),
            )
            row = cur.fetchone()
            if row and row[0]:  # xmax = 0 means inserted
                inserted += 1
            else:
                updated += 1

    conn.commit()
    return inserted, updated


def get_upcoming_events(
    conn: Connection,
    start_time: datetime,
    end_time: datetime,
    countries: Optional[list[str]] = None,
    impact_filter: Optional[list[str]] = None,
) -> list[EconomicEventRow]:
    """Get upcoming economic events within a time range.

    Args:
        conn: Database connection.
        start_time: Start of time range (UTC).
        end_time: End of time range (UTC).
        countries: Optional list of country codes to filter (e.g., ['USD']).
        impact_filter: Optional list of impact levels (e.g., ['High']).

    Returns:
        List of EconomicEventRow sorted by event_timestamp.
    """
    # Ensure UTC
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)

    query = """
        SELECT id, title, country, event_timestamp, impact, 
               forecast, previous, actual, source, fetched_at
        FROM economic_calendar_events
        WHERE event_timestamp >= %s
          AND event_timestamp <= %s
    """
    params: list[object] = [start_time, end_time]

    if countries:
        query += " AND country = ANY(%s)"
        params.append(countries)

    if impact_filter:
        query += " AND impact = ANY(%s)"
        params.append(impact_filter)

    query += " ORDER BY event_timestamp ASC"

    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    return [EconomicEventRow.from_row(row) for row in rows]


def get_last_fetch_time(
    conn: Connection,
    source: str = "forexfactory",
) -> Optional[datetime]:
    """Get the most recent fetch time for a source.

    Used to determine if data is stale and needs refresh.

    Args:
        conn: Database connection.
        source: Data source identifier.

    Returns:
        Most recent fetched_at timestamp, or None if no data exists.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT MAX(fetched_at)
            FROM economic_calendar_events
            WHERE source = %s
            """,
            (source,),
        )
        row = cur.fetchone()
        return row[0] if row and row[0] else None


def get_event_count(
    conn: Connection,
    source: str = "forexfactory",
    countries: Optional[list[str]] = None,
    impact_filter: Optional[list[str]] = None,
) -> int:
    """Get count of events matching criteria.

    Args:
        conn: Database connection.
        source: Data source identifier.
        countries: Optional list of country codes.
        impact_filter: Optional list of impact levels.

    Returns:
        Count of matching events.
    """
    query = "SELECT COUNT(*) FROM economic_calendar_events WHERE source = %s"
    params: list[object] = [source]

    if countries:
        query += " AND country = ANY(%s)"
        params.append(countries)

    if impact_filter:
        query += " AND impact = ANY(%s)"
        params.append(impact_filter)

    with conn.cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        return row[0] if row else 0


def is_data_stale(
    conn: Connection,
    stale_hours: float,
    source: str = "forexfactory",
) -> bool:
    """Check if the economic calendar data is stale.

    Args:
        conn: Database connection.
        stale_hours: Number of hours after which data is considered stale.
        source: Data source identifier.

    Returns:
        True if data is stale (last fetch > stale_hours ago or no data).
    """
    last_fetch = get_last_fetch_time(conn, source)

    if last_fetch is None:
        return True

    # Ensure both are timezone-aware for comparison
    now = datetime.now(timezone.utc)
    if last_fetch.tzinfo is None:
        last_fetch = last_fetch.replace(tzinfo=timezone.utc)

    stale_threshold = now - timedelta(hours=stale_hours)
    return last_fetch < stale_threshold


def delete_old_events(
    conn: Connection,
    days_to_keep: int = 30,
) -> int:
    """Delete old events to prevent unbounded table growth.

    Args:
        conn: Database connection.
        days_to_keep: Number of days of events to retain.

    Returns:
        Number of rows deleted.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_to_keep)

    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM economic_calendar_events
            WHERE event_timestamp < %s
            """,
            (cutoff,),
        )
        deleted = cur.rowcount

    conn.commit()
    return deleted
