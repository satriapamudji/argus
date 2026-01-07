"""Partition management for Argus database."""

from datetime import date, timedelta
from typing import Optional

from psycopg2.extensions import connection as Connection


def create_partition_for_date(conn: Connection, partition_date: date) -> str:
    """Create a partition for a specific date.

    Args:
        conn: Database connection.
        partition_date: Date to create partition for.

    Returns:
        Name of the created partition.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT create_news_items_partition(%s)", (partition_date,))
        result = cur.fetchone()
        partition_name = result[0] if result else ""
    conn.commit()
    return partition_name


def create_partitions_for_range(conn: Connection, start_date: date, end_date: date) -> list[str]:
    """Create partitions for a date range.

    Args:
        conn: Database connection.
        start_date: First date to create partition for.
        end_date: Last date (inclusive) to create partition for.

    Returns:
        List of created partition names.
    """
    created = []
    current = start_date
    while current <= end_date:
        partition_name = create_partition_for_date(conn, current)
        created.append(partition_name)
        current += timedelta(days=1)
    return created


def ensure_partition_exists(conn: Connection, partition_date: date) -> str:
    """Ensure a partition exists for the given date.

    Creates the partition if it doesn't exist.

    Args:
        conn: Database connection.
        partition_date: Date to ensure partition for.

    Returns:
        Name of the partition.
    """
    return create_partition_for_date(conn, partition_date)


def drop_old_partitions(conn: Connection, retention_days: int) -> list[str]:
    """Drop partitions older than retention_days.

    Args:
        conn: Database connection.
        retention_days: Number of days to retain partitions.

    Returns:
        List of dropped partition names.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM drop_old_news_items_partitions(%s)", (retention_days,))
        dropped = [row[0] for row in cur.fetchall()]
    conn.commit()
    return dropped


def get_existing_partitions(conn: Connection) -> list[str]:
    """Get list of existing news_items partitions.

    Args:
        conn: Database connection.

    Returns:
        List of partition names.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT c.relname AS partition_name
            FROM pg_class c
            JOIN pg_inherits i ON c.oid = i.inhrelid
            JOIN pg_class parent ON parent.oid = i.inhparent
            WHERE parent.relname = 'news_items'
            ORDER BY c.relname
        """)
        return [row[0] for row in cur.fetchall()]


def run_retention_cleanup(
    conn: Connection, news_items_days: int = 60, fingerprints_days: Optional[int] = None
) -> dict[str, list[str]]:
    """Run retention cleanup for all tables.

    Args:
        conn: Database connection.
        news_items_days: Days to retain news_items partitions.
        fingerprints_days: Optional days to retain fingerprints.
            If None, fingerprints are not cleaned up.

    Returns:
        Dictionary with 'dropped_partitions' and 'deleted_fingerprints' counts.
    """
    result: dict[str, list[str]] = {
        "dropped_partitions": [],
        "deleted_fingerprints": [],
    }

    # Drop old news_items partitions
    result["dropped_partitions"] = drop_old_partitions(conn, news_items_days)

    # Optionally clean up old fingerprints
    if fingerprints_days is not None:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM news_fingerprints 
                WHERE last_seen_at < NOW() - INTERVAL '%s days'
                RETURNING hash_url
            """,
                (fingerprints_days,),
            )
            result["deleted_fingerprints"] = [row[0] for row in cur.fetchall()]
        conn.commit()

    return result
