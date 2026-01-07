"""Near-duplicate detection with database integration.

Provides functions to check for near-duplicates within a configurable
time window using SimHash signatures stored in news_fingerprints.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from psycopg2.extensions import connection as Connection

from argus.dedupe.simhash import hamming_distance


def check_near_duplicate(
    conn: Connection,
    simhash: int,
    threshold: int = 4,
    window_days: int = 14,
    exclude_fingerprint_id: Optional[int] = None,
) -> Optional[int]:
    """Check if a SimHash has near-duplicates in the database.

    Searches news_fingerprints for entries with similar SimHash values
    (Hamming distance <= threshold) within the specified time window.

    Args:
        conn: Database connection.
        simhash: SimHash to check.
        threshold: Maximum Hamming distance for near-duplicates (default 4).
        window_days: Number of days to look back (default 14).
        exclude_fingerprint_id: Optional fingerprint ID to exclude from check.

    Returns:
        Fingerprint ID of the near-duplicate if found, None otherwise.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

    with conn.cursor() as cur:
        # Query fingerprints with simhash in the window
        # Note: PostgreSQL doesn't have built-in bit_count before v14,
        # so we fetch candidates and check in Python
        query = """
            SELECT id, simhash 
            FROM news_fingerprints 
            WHERE simhash IS NOT NULL 
              AND first_seen_at >= %s
        """
        params: list[object] = [cutoff]

        if exclude_fingerprint_id is not None:
            query += " AND id != %s"
            params.append(exclude_fingerprint_id)

        cur.execute(query, params)
        rows = cur.fetchall()

    # Check Hamming distance for each candidate
    for row in rows:
        fp_id, fp_simhash = row
        if fp_simhash is not None and hamming_distance(simhash, fp_simhash) <= threshold:
            return int(fp_id)

    return None


def find_near_duplicates(
    conn: Connection,
    simhash: int,
    threshold: int = 4,
    window_days: int = 14,
    limit: int = 10,
) -> list[tuple[int, int, int]]:
    """Find all near-duplicates of a SimHash in the database.

    Args:
        conn: Database connection.
        simhash: SimHash to check.
        threshold: Maximum Hamming distance for near-duplicates (default 4).
        window_days: Number of days to look back (default 14).
        limit: Maximum number of results to return.

    Returns:
        List of tuples (fingerprint_id, simhash, hamming_distance).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, simhash 
            FROM news_fingerprints 
            WHERE simhash IS NOT NULL 
              AND first_seen_at >= %s
            """,
            (cutoff,),
        )
        rows = cur.fetchall()

    # Find all matches and sort by distance
    matches = []
    for row in rows:
        fp_id, fp_simhash = row
        if fp_simhash is not None:
            dist = hamming_distance(simhash, fp_simhash)
            if dist <= threshold:
                matches.append((fp_id, fp_simhash, dist))

    # Sort by distance (closest first)
    matches.sort(key=lambda x: x[2])
    return matches[:limit]


def check_title_trigram_similarity(
    conn: Connection,
    title: str,
    similarity_threshold: float = 0.85,
    window_days: int = 14,
) -> Optional[int]:
    """Check if a title is too similar to existing titles using pg_trgm.

    Requires pg_trgm extension to be installed in the database.
    Falls back to None if extension is not available.

    Args:
        conn: Database connection.
        title: Title to check.
        similarity_threshold: Minimum similarity (0-1) to consider duplicate.
        window_days: Number of days to look back.

    Returns:
        News item ID of the similar title if found, None otherwise.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

    try:
        with conn.cursor() as cur:
            # Check if pg_trgm extension exists
            cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")
            if not cur.fetchone():
                # Extension not installed, skip this check
                return None

            # Use pg_trgm similarity function
            cur.execute(
                """
                SELECT ni.id, similarity(ni.title, %s) as sim
                FROM news_items ni
                WHERE ni.ingested_at >= %s
                  AND similarity(ni.title, %s) >= %s
                ORDER BY sim DESC
                LIMIT 1
                """,
                (title, cutoff, title, similarity_threshold),
            )
            row = cur.fetchone()
            if row:
                return int(row[0])
    except Exception:
        # If pg_trgm functions fail, skip this check
        pass

    return None
