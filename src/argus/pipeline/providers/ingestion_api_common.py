"""Common utilities for API-based ingestion providers.

Provides reusable components for ingesting news from external APIs:
- NormalizedArticle: API-agnostic article representation
- parse_iso_datetime: Parse ISO 8601 datetime strings
- ingest_article: Insert article into database with deduplication
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from psycopg2.extensions import connection as Connection

from argus.db.repository import (
    check_duplicate_by_url,
    get_existing_url_hashes,
    get_or_create_fingerprint,
    hash_text,
    hash_url,
    insert_news_item,
    insert_news_items_batch,
    upsert_fingerprints_batch,
)

logger = logging.getLogger(__name__)


@dataclass
class NormalizedArticle:
    """API-agnostic article representation for database insertion.

    All API ingestion providers should normalize their response data
    into this format before calling ingest_article().
    """

    url: str  # Primary deduplication key
    title: str
    source_name: str  # Domain or publisher name (e.g., "reuters.com")
    snippet: Optional[str] = None  # Description or summary text
    published_at: Optional[datetime] = None  # Parsed datetime
    author: Optional[str] = None  # Author name if available
    raw_metadata: dict = field(default_factory=dict)  # API-specific fields


def parse_iso_datetime(dt_string: Optional[str]) -> Optional[datetime]:
    """Parse ISO 8601 datetime string.

    Handles common formats from news APIs:
    - 2024-01-15T10:30:00Z
    - 2024-01-15T10:30:00.000Z
    - 2024-01-15T10:30:00+00:00
    - 2024-01-15 10:30:00

    Args:
        dt_string: ISO 8601 datetime string or None.

    Returns:
        Parsed datetime (naive, UTC assumed) or None if parsing fails.
    """
    if not dt_string:
        return None

    # Common formats to try
    formats = [
        "%Y-%m-%dT%H:%M:%SZ",  # 2024-01-15T10:30:00Z
        "%Y-%m-%dT%H:%M:%S.%fZ",  # 2024-01-15T10:30:00.000Z
        "%Y-%m-%dT%H:%M:%S%z",  # 2024-01-15T10:30:00+00:00
        "%Y-%m-%dT%H:%M:%S.%f%z",  # 2024-01-15T10:30:00.000+00:00
        "%Y-%m-%d %H:%M:%S",  # 2024-01-15 10:30:00
        "%Y-%m-%d",  # 2024-01-15
    ]

    for fmt in formats:
        try:
            parsed = datetime.strptime(dt_string, fmt)
            # Convert timezone-aware to naive (assume UTC)
            if parsed.tzinfo is not None:
                parsed = parsed.replace(tzinfo=None)
            return parsed
        except ValueError:
            continue

    logger.warning(f"Failed to parse datetime: {dt_string}")
    return None


def ingest_article(
    conn: Connection,
    article: NormalizedArticle,
    stream_name: str,
) -> bool:
    """Insert article into database with deduplication.

    Uses existing repository functions to:
    1. Check for duplicate by URL (per-stream)
    2. Create fingerprint for text-based deduplication
    3. Insert news item

    Args:
        conn: Database connection.
        article: Normalized article to insert.
        stream_name: Stream name for per-stream deduplication.

    Returns:
        True if article was new and inserted, False if duplicate.
    """
    # Check for duplicate by URL
    if check_duplicate_by_url(conn, article.url, stream_name=stream_name):
        logger.debug(f"Duplicate URL skipped: {article.url}")
        return False

    # Create fingerprint (handles text hash)
    fingerprint, was_created = get_or_create_fingerprint(
        conn=conn,
        url=article.url,
        source_name=article.source_name,
        stream_name=stream_name,
        title=article.title,
        snippet=article.snippet,
    )

    if not was_created:
        # Fingerprint already existed (shouldn't happen if URL check passed, but safety)
        logger.debug(f"Fingerprint already exists for: {article.url}")
        return False

    # Insert news item
    insert_news_item(
        conn=conn,
        fingerprint_id=fingerprint.id,
        source_name=article.source_name,
        source_url=article.url,
        title=article.title,
        stream_name=stream_name,
        snippet=article.snippet,
        author=article.author,
        published_at=article.published_at,
        raw_metadata=article.raw_metadata,
    )

    logger.info(f"Ingested: {article.title[:50]}...")
    return True


def ingest_articles_batch(
    conn: Connection,
    articles: list[NormalizedArticle],
    stream_name: str,
) -> tuple[int, int]:
    """Insert multiple articles into the database with deduplication.

    Args:
        conn: Database connection.
        articles: Normalized articles to insert.
        stream_name: Stream name for per-stream deduplication.

    Returns:
        Tuple of (new_count, duplicate_count).
    """
    if not articles:
        return 0, 0

    seen_hashes: set[str] = set()
    unique_articles: list[tuple[NormalizedArticle, str]] = []
    duplicate_in_batch = 0

    for article in articles:
        url_hash = hash_url(article.url)
        if url_hash in seen_hashes:
            duplicate_in_batch += 1
            continue
        seen_hashes.add(url_hash)
        unique_articles.append((article, url_hash))

    existing_hashes = get_existing_url_hashes(
        conn,
        stream_name,
        [url_hash for _, url_hash in unique_articles],
    )

    new_articles = [
        (article, url_hash)
        for article, url_hash in unique_articles
        if url_hash not in existing_hashes
    ]
    duplicate_count = duplicate_in_batch + len(existing_hashes)

    if not new_articles:
        return 0, duplicate_count

    fingerprint_rows = [
        (
            stream_name,
            url_hash,
            hash_text(article.title, article.snippet) if article.title else None,
            None,
            article.source_name,
        )
        for article, url_hash in new_articles
    ]
    fingerprints = upsert_fingerprints_batch(conn, fingerprint_rows)
    fingerprint_by_hash = {fp.hash_url: fp for fp in fingerprints}

    ingested_at = datetime.now(timezone.utc)
    news_rows = []
    for article, url_hash in new_articles:
        fingerprint = fingerprint_by_hash.get(url_hash)
        if fingerprint is None:
            continue
        news_rows.append(
            (
                stream_name,
                fingerprint.id,
                article.source_name,
                article.url,
                article.title,
                article.snippet,
                article.author,
                article.published_at,
                ingested_at,
                article.raw_metadata or None,
            )
        )

    insert_news_items_batch(conn, news_rows)
    logger.info(f"Ingested batch: {len(new_articles)} new, {duplicate_count} duplicates")
    return len(new_articles), duplicate_count
