"""Repository layer for database operations."""

import hashlib
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from psycopg2.extensions import connection as Connection

from datetime import date

from argus.db.models import (
    MessageRow,
    NewsFingerprintRow,
    NewsItemRow,
    RunRow,
)
from argus.db.partitions import ensure_partition_exists


def normalize_url(url: str) -> str:
    """Normalize a URL for hashing.

    Removes trailing slashes, lowercases, strips protocol variants.

    Args:
        url: URL to normalize.

    Returns:
        Normalized URL string.
    """
    url = url.strip().lower()
    # Remove trailing slash
    url = url.rstrip("/")
    # Normalize http/https
    if url.startswith("https://"):
        url = url[8:]
    elif url.startswith("http://"):
        url = url[7:]
    # Remove www.
    if url.startswith("www."):
        url = url[4:]
    return url


def hash_url(url: str) -> str:
    """Generate SHA256 hash of normalized URL.

    Args:
        url: URL to hash.

    Returns:
        64-character hex string.
    """
    normalized = normalize_url(url)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def hash_text(title: str, snippet: Optional[str] = None) -> str:
    """Generate SHA256 hash of normalized title + snippet.

    Args:
        title: Title text.
        snippet: Optional snippet text.

    Returns:
        64-character hex string.
    """
    text = title.strip().lower()
    if snippet:
        text += " " + snippet.strip().lower()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_or_create_fingerprint(
    conn: Connection,
    url: str,
    source_name: str,
    stream_name: str = "us_markets",
    title: Optional[str] = None,
    snippet: Optional[str] = None,
    simhash: Optional[int] = None,
) -> tuple[NewsFingerprintRow, bool]:
    """Get or create a fingerprint for a news item.

    Args:
        conn: Database connection.
        url: News item URL.
        source_name: Source name.
        stream_name: Stream name (e.g., 'us_markets', 'asia_markets').
        title: Optional title for text hash.
        snippet: Optional snippet for text hash.
        simhash: Optional SimHash value.

    Returns:
        Tuple of (fingerprint row, was_created).
    """
    url_hash = hash_url(url)
    text_hash = hash_text(title, snippet) if title else None

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO news_fingerprints
                (stream_name, hash_url, hash_text, simhash, source_name)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (stream_name, hash_url)
            DO UPDATE SET last_seen_at = NOW()
            RETURNING
                id,
                stream_name,
                hash_url,
                hash_text,
                simhash,
                source_name,
                first_seen_at,
                last_seen_at,
                (xmax = 0) AS inserted
            """,
            (stream_name, url_hash, text_hash, simhash, source_name),
        )
        row = cur.fetchone()
        conn.commit()

        if row:
            return NewsFingerprintRow.from_row(row[:8]), bool(row[8])
        raise RuntimeError("Failed to create fingerprint")


def insert_news_item(
    conn: Connection,
    fingerprint_id: int,
    source_name: str,
    source_url: str,
    title: str,
    stream_name: str = "us_markets",
    snippet: Optional[str] = None,
    author: Optional[str] = None,
    published_at: Optional[datetime] = None,
    raw_metadata: Optional[dict[str, Any]] = None,
    ingested_at: Optional[datetime] = None,
) -> NewsItemRow:
    """Insert a news item.

    Args:
        conn: Database connection.
        fingerprint_id: ID of the fingerprint.
        source_name: Source name.
        source_url: Full URL.
        title: Title text.
        stream_name: Stream name (e.g., 'us_markets', 'asia_markets').
        snippet: Optional snippet.
        author: Optional author.
        published_at: Optional publication timestamp.
        raw_metadata: Optional raw metadata dict.
        ingested_at: Optional ingestion timestamp (defaults to now).

    Returns:
        Created NewsItemRow.
    """
    import json

    if ingested_at is None:
        ingested_at = datetime.now(timezone.utc)

    # Ensure partition exists for this stream and date
    ensure_partition_exists(conn, ingested_at.date(), stream_name=stream_name)

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO news_items 
                (stream_name, fingerprint_id, source_name, source_url, title, snippet, 
                 author, published_at, ingested_at, raw_metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                stream_name,
                fingerprint_id,
                source_name,
                source_url,
                title,
                snippet,
                author,
                published_at,
                ingested_at,
                json.dumps(raw_metadata) if raw_metadata else None,
            ),
        )
        row = cur.fetchone()
        conn.commit()

        if row:
            return NewsItemRow.from_row(row)
        raise RuntimeError("Failed to insert news item")


def insert_news_items_batch(
    conn: Connection,
    rows: Sequence[
        tuple[
            str,
            int,
            str,
            str,
            str,
            Optional[str],
            Optional[str],
            Optional[datetime],
            datetime,
            Optional[dict[str, Any]],
        ]
    ],
) -> list[NewsItemRow]:
    """Insert multiple news items in a single query.

    Args:
        conn: Database connection.
        rows: Sequence of tuples matching news_items columns.

    Returns:
        List of created NewsItemRow objects.
    """
    from psycopg2.extras import Json, execute_values

    if not rows:
        return []

    dates = {row[8].date() for row in rows}
    stream_name = rows[0][0]
    for partition_date in dates:
        ensure_partition_exists(conn, partition_date, stream_name=stream_name)

    values = []
    for row in rows:
        raw_metadata = Json(row[9]) if row[9] else None
        values.append((*row[:9], raw_metadata))

    with conn.cursor() as cur:
        inserted = execute_values(
            cur,
            """
            INSERT INTO news_items
                (stream_name, fingerprint_id, source_name, source_url, title, snippet,
                 author, published_at, ingested_at, raw_metadata)
            VALUES %s
            RETURNING *
            """,
            values,
            fetch=True,
        )
    conn.commit()

    return [NewsItemRow.from_row(row) for row in inserted]


def create_run(
    conn: Connection,
    stream_name: str,
    run_mode: str,
) -> RunRow:
    """Create a new run record.

    Args:
        conn: Database connection.
        stream_name: Name of the stream.
        run_mode: Run mode ('us_close', 'weekend_wrap', 'monday_preview').

    Returns:
        Created RunRow.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO runs (stream_name, run_mode, status)
            VALUES (%s, %s, 'running')
            RETURNING *
            """,
            (stream_name, run_mode),
        )
        row = cur.fetchone()
        conn.commit()

        if row:
            return RunRow.from_row(row)
        raise RuntimeError("Failed to create run")


def update_run(
    conn: Connection,
    run_id: int,
    status: Optional[str] = None,
    facts_bundle_json: Optional[dict[str, Any]] = None,
    timings_json: Optional[dict[str, Any]] = None,
    risk_score: Optional[int] = None,
    calendar_score: Optional[int] = None,
    market_score: Optional[int] = None,
    headline_score: Optional[int] = None,
    error_message: Optional[str] = None,
    completed_at: Optional[datetime] = None,
) -> None:
    """Update a run record.

    Args:
        conn: Database connection.
        run_id: ID of the run to update.
        status: Optional new status.
        facts_bundle_json: Optional facts bundle.
        timings_json: Optional timings.
        risk_score: Optional risk score.
        calendar_score: Optional calendar score.
        market_score: Optional market score.
        headline_score: Optional headline score.
        error_message: Optional error message.
        completed_at: Optional completion timestamp.
    """
    import json

    updates = []
    values: list[Any] = []

    if status is not None:
        updates.append("status = %s")
        values.append(status)
    if facts_bundle_json is not None:
        updates.append("facts_bundle_json = %s")
        values.append(json.dumps(facts_bundle_json))
    if timings_json is not None:
        updates.append("timings_json = %s")
        values.append(json.dumps(timings_json))
    if risk_score is not None:
        updates.append("risk_score = %s")
        values.append(risk_score)
    if calendar_score is not None:
        updates.append("calendar_score = %s")
        values.append(calendar_score)
    if market_score is not None:
        updates.append("market_score = %s")
        values.append(market_score)
    if headline_score is not None:
        updates.append("headline_score = %s")
        values.append(headline_score)
    if error_message is not None:
        updates.append("error_message = %s")
        values.append(error_message)
    if completed_at is not None:
        updates.append("completed_at = %s")
        values.append(completed_at)

    if not updates:
        return

    values.append(run_id)

    with conn.cursor() as cur:
        cur.execute(f"UPDATE runs SET {', '.join(updates)} WHERE id = %s", values)
    conn.commit()


def create_message(
    conn: Connection,
    run_id: int,
    content: str,
) -> MessageRow:
    """Create a new message record.

    Args:
        conn: Database connection.
        run_id: ID of the run.
        content: Message content.

    Returns:
        Created MessageRow.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO messages (run_id, content)
            VALUES (%s, %s)
            RETURNING *
            """,
            (run_id, content),
        )
        row = cur.fetchone()
        conn.commit()

        if row:
            return MessageRow.from_row(row)
        raise RuntimeError("Failed to create message")


def update_message(
    conn: Connection,
    message_id: int,
    validation_status: Optional[str] = None,
    validation_errors: Optional[list[str]] = None,
    publish_status: Optional[str] = None,
    telegram_message_id: Optional[int] = None,
    published_at: Optional[datetime] = None,
) -> None:
    """Update a message record.

    Args:
        conn: Database connection.
        message_id: ID of the message to update.
        validation_status: Optional validation status.
        validation_errors: Optional validation errors.
        publish_status: Optional publish status.
        telegram_message_id: Optional Telegram message ID.
        published_at: Optional publish timestamp.
    """
    import json

    updates = []
    values: list[Any] = []

    if validation_status is not None:
        updates.append("validation_status = %s")
        values.append(validation_status)
    if validation_errors is not None:
        updates.append("validation_errors = %s")
        values.append(json.dumps(validation_errors))
    if publish_status is not None:
        updates.append("publish_status = %s")
        values.append(publish_status)
    if telegram_message_id is not None:
        updates.append("telegram_message_id = %s")
        values.append(telegram_message_id)
    if published_at is not None:
        updates.append("published_at = %s")
        values.append(published_at)

    if not updates:
        return

    values.append(message_id)

    with conn.cursor() as cur:
        cur.execute(f"UPDATE messages SET {', '.join(updates)} WHERE id = %s", values)
    conn.commit()


def check_duplicate_by_url(
    conn: Connection,
    url: str,
    stream_name: str = "us_markets",
) -> bool:
    """Check if a URL has already been ingested for this stream.

    Args:
        conn: Database connection.
        url: URL to check.
        stream_name: Stream name for per-stream deduplication.

    Returns:
        True if duplicate exists in this stream.
    """
    url_hash = hash_url(url)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM news_fingerprints WHERE stream_name = %s AND hash_url = %s LIMIT 1",
            (stream_name, url_hash),
        )
    return cur.fetchone() is not None


def get_existing_url_hashes(
    conn: Connection,
    stream_name: str,
    url_hashes: Sequence[str],
) -> set[str]:
    """Return existing URL hashes for a stream.

    Args:
        conn: Database connection.
        stream_name: Stream name for per-stream deduplication.
        url_hashes: Sequence of URL hashes to check.

    Returns:
        Set of hashes that already exist.
    """
    if not url_hashes:
        return set()

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT hash_url
            FROM news_fingerprints
            WHERE stream_name = %s
              AND hash_url = ANY(%s)
            """,
            (stream_name, list(url_hashes)),
        )
        return {row[0] for row in cur.fetchall()}


def upsert_fingerprints_batch(
    conn: Connection,
    rows: Sequence[tuple[str, str, Optional[str], Optional[int], str]],
) -> list[NewsFingerprintRow]:
    """Upsert multiple fingerprints in a single query.

    Args:
        conn: Database connection.
        rows: Sequence of tuples for news_fingerprints values.

    Returns:
        List of NewsFingerprintRow objects for inserted/updated rows.
    """
    from psycopg2.extras import execute_values

    if not rows:
        return []

    with conn.cursor() as cur:
        inserted = execute_values(
            cur,
            """
            INSERT INTO news_fingerprints
                (stream_name, hash_url, hash_text, simhash, source_name)
            VALUES %s
            ON CONFLICT (stream_name, hash_url)
            DO UPDATE SET last_seen_at = NOW()
            RETURNING id, stream_name, hash_url, hash_text, simhash, source_name,
                      first_seen_at, last_seen_at
            """,
            rows,
            fetch=True,
        )
    conn.commit()

    return [NewsFingerprintRow.from_row(row) for row in inserted]


def check_duplicate_by_text(
    conn: Connection,
    title: str,
    snippet: Optional[str] = None,
    stream_name: str = "us_markets",
) -> bool:
    """Check if text content has already been ingested for this stream.

    Args:
        conn: Database connection.
        title: Title text.
        snippet: Optional snippet.
        stream_name: Stream name for per-stream deduplication.

    Returns:
        True if duplicate exists in this stream.
    """
    text_hash_value = hash_text(title, snippet)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM news_fingerprints WHERE stream_name = %s AND hash_text = %s LIMIT 1",
            (stream_name, text_hash_value),
        )
        return cur.fetchone() is not None


def check_near_duplicate_by_simhash(
    conn: Connection,
    simhash: int,
    threshold: int = 4,
    window_days: int = 14,
    exclude_fingerprint_id: Optional[int] = None,
    stream_name: Optional[str] = None,
) -> Optional[int]:
    """Check if a SimHash has near-duplicates in the database.

    Wrapper around dedupe.check_near_duplicate for repository layer.

    Args:
        conn: Database connection.
        simhash: SimHash to check.
        threshold: Maximum Hamming distance for near-duplicates (default 4).
        window_days: Number of days to look back (default 14).
        exclude_fingerprint_id: Optional fingerprint ID to exclude from check.
        stream_name: Optional stream name for per-stream deduplication.

    Returns:
        Fingerprint ID of the near-duplicate if found, None otherwise.
    """
    from argus.dedupe.near_duplicate import check_near_duplicate

    return check_near_duplicate(
        conn=conn,
        simhash=simhash,
        threshold=threshold,
        window_days=window_days,
        exclude_fingerprint_id=exclude_fingerprint_id,
        stream_name=stream_name,
    )


def get_or_create_fingerprint_with_dedupe(
    conn: Connection,
    url: str,
    source_name: str,
    stream_name: str = "us_markets",
    title: Optional[str] = None,
    snippet: Optional[str] = None,
    simhash_enabled: bool = True,
    simhash_threshold: int = 4,
    simhash_window_days: int = 14,
) -> tuple[NewsFingerprintRow, bool, Optional[int]]:
    """Get or create a fingerprint with full dedupe checking.

    Performs:
    1. Exact URL hash check (per-stream)
    2. SimHash near-duplicate check (if enabled and title provided)
    3. Creates fingerprint with computed SimHash

    Args:
        conn: Database connection.
        url: News item URL.
        source_name: Source name.
        stream_name: Stream name (e.g., 'us_markets', 'asia_markets').
        title: Optional title for SimHash/text hash.
        snippet: Optional snippet for SimHash/text hash.
        simhash_enabled: Whether to check/compute SimHash.
        simhash_threshold: Hamming distance threshold for near-duplicates.
        simhash_window_days: Number of days to look back for near-duplicates.

    Returns:
        Tuple of:
        - fingerprint row
        - was_created (False if existing URL match)
        - near_duplicate_id (fingerprint ID if SimHash match found, None otherwise)
    """
    url_hash = hash_url(url)

    with conn.cursor() as cur:
        # Check for exact URL match first (per-stream deduplication)
        cur.execute(
            "SELECT * FROM news_fingerprints WHERE stream_name = %s AND hash_url = %s",
            (stream_name, url_hash),
        )
        row = cur.fetchone()

        if row:
            # Exact URL match - update last_seen_at and return
            cur.execute(
                "UPDATE news_fingerprints SET last_seen_at = NOW() WHERE id = %s", (row[0],)
            )
            conn.commit()
            return NewsFingerprintRow.from_row(row), False, None

    # Compute SimHash if enabled and we have text
    simhash_value: Optional[int] = None
    near_duplicate_id: Optional[int] = None

    if simhash_enabled and title:
        from argus.dedupe.simhash import compute_simhash

        text = title
        if snippet:
            text += " " + snippet
        simhash_value = compute_simhash(text)

        # Check for near-duplicates (within the same stream)
        near_duplicate_id = check_near_duplicate_by_simhash(
            conn=conn,
            simhash=simhash_value,
            threshold=simhash_threshold,
            window_days=simhash_window_days,
            stream_name=stream_name,
        )

    # Create new fingerprint (even if near-duplicate found - caller decides what to do)
    text_hash = hash_text(title, snippet) if title else None

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO news_fingerprints 
                (stream_name, hash_url, hash_text, simhash, source_name)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
            """,
            (stream_name, url_hash, text_hash, simhash_value, source_name),
        )
        row = cur.fetchone()
        conn.commit()

        if row:
            return NewsFingerprintRow.from_row(row), True, near_duplicate_id
        raise RuntimeError("Failed to create fingerprint")


# =============================================================================
# Enrichment repository functions
# =============================================================================


def get_news_items_for_enrichment(
    conn: Connection,
    window_hours: int = 24,
    limit: int = 25,
    stream_name: str = "us_markets",
) -> list[tuple[int, str, str, datetime, int]]:
    """Get news items eligible for enrichment.

    Selects top K items by impact_score that don't already have content.

    Args:
        conn: Database connection.
        window_hours: Look back window in hours.
        limit: Maximum number of items to return.
        stream_name: Stream name to filter items (e.g., 'us_markets', 'crypto').

    Returns:
        List of tuples: (id, source_url, title, ingested_at, impact_score)
    """
    query = """
        SELECT ni.id, ni.source_url, ni.title, ni.ingested_at, ns.impact_score
        FROM news_items ni
        JOIN news_scores ns
          ON ni.id = ns.news_item_id
         AND ns.stream_name = ni.stream_name
        LEFT JOIN news_content nc
          ON ni.id = nc.news_item_id
         AND nc.stream_name = ni.stream_name
        WHERE ni.ingested_at >= NOW() - INTERVAL '%s hours'
          AND ni.stream_name = %s
          AND nc.id IS NULL
        ORDER BY ns.impact_score DESC
        LIMIT %s
    """

    with conn.cursor() as cur:
        cur.execute(query, (window_hours, stream_name, limit))
        return cur.fetchall()


def has_news_content(conn: Connection, news_item_id: int) -> bool:
    """Check if a news item already has content stored.

    Args:
        conn: Database connection.
        news_item_id: ID of the news item.

    Returns:
        True if content exists.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM news_content WHERE news_item_id = %s LIMIT 1",
            (news_item_id,),
        )
        return cur.fetchone() is not None


def insert_news_content(
    conn: Connection,
    news_item_id: int,
    ingested_at: datetime,
    content_type: str,
    content: str,
    content_hash: str,
    content_status: str = "success",
    stream_name: str = "us_markets",
) -> int:
    """Insert content into news_content table.

    Args:
        conn: Database connection.
        news_item_id: ID of the news item.
        ingested_at: Ingestion timestamp (denormalized for partition pruning).
        content_type: 'excerpt' or 'full_text'.
        content: The content text.
        content_hash: SHA256 hash of content.
        content_status: 'success', 'failed', or 'pending'.
        stream_name: Stream name (e.g., 'us_markets', 'asia_markets').

    Returns:
        ID of the inserted row.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO news_content 
                (news_item_id, stream_name, ingested_at, content_type, content, content_hash, content_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                news_item_id,
                stream_name,
                ingested_at,
                content_type,
                content,
                content_hash,
                content_status,
            ),
        )
        row = cur.fetchone()
        conn.commit()

        if row:
            return row[0]
        raise RuntimeError("Failed to insert news content")


# =============================================================================
# Scoring repository functions
# =============================================================================


def get_news_items_for_scoring(
    conn: Connection,
    window_hours: int = 24,
    limit: int = 100,
    stream_name: str = "us_markets",
) -> list[
    tuple[int, int, str, str, str, Optional[str], Optional[datetime], datetime, Optional[int]]
]:
    """Get news items eligible for scoring.

    Returns items from the window that don't already have scores.

    Args:
        conn: Database connection.
        window_hours: Look back window in hours.
        limit: Maximum number of items to return.
        stream_name: Stream name to filter items (e.g., 'us_markets', 'crypto').

    Returns:
        List of tuples: (id, fingerprint_id, source_name, source_url, title,
                         snippet, published_at, ingested_at, simhash)
    """
    query = """
        SELECT 
            ni.id,
            ni.fingerprint_id,
            ni.source_name,
            ni.source_url,
            ni.title,
            ni.snippet,
            ni.published_at,
            ni.ingested_at,
            nf.simhash
        FROM news_items ni
        JOIN news_fingerprints nf
          ON ni.fingerprint_id = nf.id
         AND nf.stream_name = ni.stream_name
        LEFT JOIN news_scores ns
          ON ni.id = ns.news_item_id
         AND ns.stream_name = ni.stream_name
        WHERE ni.ingested_at >= NOW() - INTERVAL '%s hours'
          AND ni.stream_name = %s
          AND ns.id IS NULL
        ORDER BY ni.ingested_at DESC
        LIMIT %s
    """

    with conn.cursor() as cur:
        cur.execute(query, (window_hours, stream_name, limit))
        return cur.fetchall()


def get_recent_simhashes(
    conn: Connection,
    window_hours: int = 24,
    stream_name: str = "us_markets",
) -> list[int]:
    """Get SimHashes from recent items for uniqueness comparison.

    Returns SimHashes from ALL recent items, including already-scored ones.

    Args:
        conn: Database connection.
        window_hours: Look back window in hours.
        stream_name: Stream name to filter items (e.g., 'us_markets', 'crypto').

    Returns:
        List of SimHash integers.
    """
    query = """
        SELECT DISTINCT nf.simhash
        FROM news_fingerprints nf
        JOIN news_items ni ON nf.id = ni.fingerprint_id
        WHERE ni.ingested_at >= NOW() - INTERVAL '%s hours'
          AND ni.stream_name = %s
          AND nf.simhash IS NOT NULL
    """

    with conn.cursor() as cur:
        cur.execute(query, (window_hours, stream_name))
        return [row[0] for row in cur.fetchall() if row[0] is not None]


def has_news_score(conn: Connection, news_item_id: int) -> bool:
    """Check if a news item already has a score.

    Args:
        conn: Database connection.
        news_item_id: ID of the news item.

    Returns:
        True if score exists.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM news_scores WHERE news_item_id = %s LIMIT 1",
            (news_item_id,),
        )
        return cur.fetchone() is not None


def insert_news_score(
    conn: Connection,
    news_item_id: int,
    ingested_at: datetime,
    impact_score: int,
    quality_score: int,
    confidence_score: int,
    scorer_version: str,
    stream_name: str = "us_markets",
    topic: Optional[str] = None,
    flags: Optional[list[str]] = None,
    reasons: Optional[list[str]] = None,
) -> int:
    """Insert a score into the news_scores table.

    Args:
        conn: Database connection.
        news_item_id: ID of the news item.
        ingested_at: Ingestion timestamp (denormalized for partition pruning).
        impact_score: Impact score (0-100).
        quality_score: Quality score (0-100).
        confidence_score: Confidence score (0-100).
        scorer_version: Version string of the scorer.
        stream_name: Stream name (e.g., 'us_markets', 'asia_markets').
        topic: Optional detected topic.
        flags: Optional list of flags.
        reasons: Optional list of score reasons.

    Returns:
        ID of the inserted row.
    """
    import json

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO news_scores 
                (news_item_id, stream_name, ingested_at, impact_score, quality_score, 
                 confidence_score, topic, flags, reasons, scorer_version)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                news_item_id,
                stream_name,
                ingested_at,
                impact_score,
                quality_score,
                confidence_score,
                topic,
                json.dumps(flags) if flags else None,
                json.dumps(reasons) if reasons else None,
                scorer_version,
            ),
        )
        row = cur.fetchone()
        conn.commit()

        if row:
            return row[0]
        raise RuntimeError("Failed to insert news score")


def get_top_scored_items(
    conn: Connection,
    window_hours: int = 24,
    limit: int = 10,
) -> list[tuple[int, str, str, int, Optional[str]]]:
    """Get top scored news items from the window.

    Args:
        conn: Database connection.
        window_hours: Look back window in hours.
        limit: Maximum number of items to return.

    Returns:
        List of tuples: (news_item_id, title, source_name, impact_score, topic)
    """
    query = """
        SELECT 
            ni.id,
            ni.title,
            ni.source_name,
            ns.impact_score,
            ns.topic
        FROM news_items ni
        JOIN news_scores ns ON ni.id = ns.news_item_id
        WHERE ni.ingested_at >= NOW() - INTERVAL '%s hours'
        ORDER BY ns.impact_score DESC
        LIMIT %s
    """

    with conn.cursor() as cur:
        cur.execute(query, (window_hours, limit))
        return cur.fetchall()


def get_daily_market_snapshots_in_range(
    conn: Connection,
    stream_name: str,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """Fetch daily market snapshots for a date range, inclusive.

    Returns raw rows as dicts (rather than typed dataclasses) since the consumer
    for weekly stats only needs numeric fields.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                trading_date,
                sp500_close,
                dow_close,
                nasdaq_close,
                vix_close,
                usd_dxy_close,
                us10y_yield,
                wti_crude_close,
                gold_close
            FROM daily_market_snapshots
            WHERE stream_name = %s
              AND trading_date >= %s
              AND trading_date <= %s
            ORDER BY trading_date ASC
            """,
            (stream_name, start_date, end_date),
        )
        rows = cur.fetchall()

    results: list[dict[str, Any]] = []
    for row in rows:
        results.append(
            {
                "trading_date": row[0],
                "sp500_close": row[1],
                "dow_close": row[2],
                "nasdaq_close": row[3],
                "vix_close": row[4],
                "usd_dxy_close": row[5],
                "us10y_yield": row[6],
                "wti_crude_close": row[7],
                "gold_close": row[8],
            }
        )

    return results


def get_last_daily_market_snapshot_before_date(
    conn: Connection,
    stream_name: str,
    before_date: date,
) -> Optional[dict[str, Any]]:
    """Fetch the last snapshot strictly before a given date."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                trading_date,
                sp500_close,
                dow_close,
                nasdaq_close,
                vix_close,
                usd_dxy_close,
                us10y_yield,
                wti_crude_close,
                gold_close
            FROM daily_market_snapshots
            WHERE stream_name = %s
              AND trading_date < %s
            ORDER BY trading_date DESC
            LIMIT 1
            """,
            (stream_name, before_date),
        )
        row = cur.fetchone()

    if row is None:
        return None

    return {
        "trading_date": row[0],
        "sp500_close": row[1],
        "dow_close": row[2],
        "nasdaq_close": row[3],
        "vix_close": row[4],
        "usd_dxy_close": row[5],
        "us10y_yield": row[6],
        "wti_crude_close": row[7],
        "gold_close": row[8],
    }


# =============================================================================
# Facts Bundle repository functions
# =============================================================================


def get_scored_items_for_bundle(
    conn: Connection,
    window_hours: int = 24,
    limit: int = 100,
    stream_name: str = "us_markets",
) -> list[dict[str, Any]]:
    """Get scored news items for facts bundle building.

    Returns items with scores, content (if enriched), and all fields
    needed for BundleCandidate construction.

    Args:
        conn: Database connection.
        window_hours: Look back window in hours.
        limit: Maximum number of items to return.
        stream_name: Stream name to filter items (e.g., 'us_markets', 'crypto').

    Returns:
        List of dicts with keys: id, title, source_name, source_url,
        published_at, ingested_at, snippet, content_excerpt, topic,
        impact_score, has_content.
    """
    query = """
        SELECT 
            ni.id,
            ni.title,
            ni.source_name,
            ni.source_url,
            ni.published_at,
            ni.ingested_at,
            ni.snippet,
            nc.content AS content_excerpt,
            ns.topic,
            ns.impact_score,
            CASE WHEN nc.id IS NOT NULL THEN TRUE ELSE FALSE END AS has_content
        FROM news_items ni
        JOIN news_scores ns
          ON ni.id = ns.news_item_id
         AND ns.stream_name = ni.stream_name
        LEFT JOIN news_content nc
          ON ni.id = nc.news_item_id
         AND nc.stream_name = ni.stream_name
        WHERE ni.ingested_at >= NOW() - INTERVAL '%s hours'
          AND ni.stream_name = %s
        ORDER BY ns.impact_score DESC, ni.id ASC
        LIMIT %s
    """

    with conn.cursor() as cur:
        cur.execute(query, (window_hours, stream_name, limit))
        rows = cur.fetchall()

    # Convert to list of dicts
    results = []
    for row in rows:
        results.append(
            {
                "id": row[0],
                "title": row[1],
                "source_name": row[2],
                "source_url": row[3],
                "published_at": row[4],
                "ingested_at": row[5],
                "snippet": row[6],
                "content_excerpt": row[7],
                "topic": row[8],
                "impact_score": row[9],
                "has_content": row[10],
            }
        )

    return results


# =============================================================================
# Message repository functions
# =============================================================================


def get_message_by_id(conn: Connection, message_id: int) -> Optional[MessageRow]:
    """Get a message by ID.

    Args:
        conn: Database connection.
        message_id: ID of the message to fetch.

    Returns:
        MessageRow if found, None otherwise.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM messages WHERE id = %s", (message_id,))
        row = cur.fetchone()

        if row:
            return MessageRow.from_row(row)
        return None


def get_messages_by_run_id(conn: Connection, run_id: int) -> list[MessageRow]:
    """Get all messages for a run.

    Args:
        conn: Database connection.
        run_id: ID of the run.

    Returns:
        List of MessageRow objects.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM messages WHERE run_id = %s ORDER BY created_at",
            (run_id,),
        )
        rows = cur.fetchall()

    return [MessageRow.from_row(row) for row in rows]


def get_pending_messages(conn: Connection, limit: int = 10) -> list[MessageRow]:
    """Get messages with pending publish status.

    Args:
        conn: Database connection.
        limit: Maximum number of messages to return.

    Returns:
        List of MessageRow objects with publish_status='pending'.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT * FROM messages 
            WHERE publish_status = 'pending' 
                AND validation_status IN ('valid', 'fallback')
            ORDER BY created_at
            LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()

    return [MessageRow.from_row(row) for row in rows]
