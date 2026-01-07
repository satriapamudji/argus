"""RSS ingestion worker for Argus."""

import logging
from dataclasses import dataclass, field
from typing import Optional

from psycopg2.extensions import connection as Connection

from argus.config import ArgusConfig
from argus.db.connection import get_connection
from argus.db.repository import (
    check_duplicate_by_url,
    get_or_create_fingerprint,
    insert_news_item,
)
from argus.ingestion.rss_parser import parse_feed
from argus.ingestion.types import RSSEntry

logger = logging.getLogger(__name__)


@dataclass
class IngestionStats:
    """Statistics from an ingestion run."""

    feeds_processed: int = 0
    feeds_failed: int = 0
    entries_found: int = 0
    entries_new: int = 0
    entries_duplicate: int = 0
    errors: list[str] = field(default_factory=list)


class RSSWorker:
    """RSS ingestion worker.

    Polls RSS feeds and ingests new items into the database.
    Designed to be triggered by cron - each invocation polls all feeds once.
    """

    def __init__(self, config: ArgusConfig, conn: Optional[Connection] = None) -> None:
        """Initialize the RSS worker.

        Args:
            config: Argus configuration.
            conn: Optional database connection. If not provided, creates one.
        """
        self.config = config
        self._conn = conn
        self._owns_connection = conn is None

    @property
    def conn(self) -> Connection:
        """Get or create database connection."""
        if self._conn is None:
            self._conn = get_connection()
        return self._conn

    def close(self) -> None:
        """Close database connection if we own it."""
        if self._owns_connection and self._conn is not None:
            self._conn.close()
            self._conn = None

    def ingest_entry(self, entry: RSSEntry) -> bool:
        """Ingest a single RSS entry into the database.

        Args:
            entry: RSS entry to ingest.

        Returns:
            True if entry was new and inserted, False if duplicate.
        """
        # Check for duplicate by URL
        if check_duplicate_by_url(self.conn, entry.source_url):
            logger.debug(f"Duplicate URL skipped: {entry.source_url}")
            return False

        # Create fingerprint (handles text hash)
        fingerprint, was_created = get_or_create_fingerprint(
            conn=self.conn,
            url=entry.source_url,
            source_name=entry.source_name,
            title=entry.title,
            snippet=entry.snippet,
        )

        if not was_created:
            # Fingerprint already existed (shouldn't happen if URL check passed, but safety)
            logger.debug(f"Fingerprint already exists for: {entry.source_url}")
            return False

        # Insert news item
        insert_news_item(
            conn=self.conn,
            fingerprint_id=fingerprint.id,
            source_name=entry.source_name,
            source_url=entry.source_url,
            title=entry.title,
            snippet=entry.snippet,
            author=entry.author,
            published_at=entry.published_at,
            raw_metadata=entry.raw_metadata,
        )

        logger.info(f"Ingested: {entry.title[:50]}...")
        return True

    def ingest_feed(self, feed_url: str) -> tuple[int, int, Optional[str]]:
        """Ingest all entries from a single feed.

        Args:
            feed_url: URL of the RSS feed.

        Returns:
            Tuple of (new_count, duplicate_count, error_message or None).
        """
        max_snippet_chars = self.config.stream.enrichment.snippet_chars
        entries, error = parse_feed(feed_url, max_snippet_chars=max_snippet_chars)

        if error:
            return 0, 0, error

        new_count = 0
        duplicate_count = 0

        for entry in entries:
            try:
                if self.ingest_entry(entry):
                    new_count += 1
                else:
                    duplicate_count += 1
            except Exception:
                logger.exception(f"Error ingesting entry: {entry.source_url}")
                # Continue with other entries

        return new_count, duplicate_count, None

    def run(self) -> IngestionStats:
        """Run ingestion for all configured feeds.

        Returns:
            IngestionStats with results.
        """
        stats = IngestionStats()
        feed_urls = self.config.get_rss_feeds()

        if not feed_urls:
            logger.warning("No RSS feeds configured")
            return stats

        logger.info(f"Starting ingestion for {len(feed_urls)} feeds")

        for feed_url in feed_urls:
            try:
                new_count, dup_count, error = self.ingest_feed(feed_url)

                if error:
                    stats.feeds_failed += 1
                    stats.errors.append(f"{feed_url}: {error}")
                    logger.error(f"Feed failed: {feed_url} - {error}")
                else:
                    stats.feeds_processed += 1
                    stats.entries_new += new_count
                    stats.entries_duplicate += dup_count
                    stats.entries_found += new_count + dup_count

            except Exception as e:
                stats.feeds_failed += 1
                stats.errors.append(f"{feed_url}: {e}")
                logger.exception(f"Unexpected error for feed: {feed_url}")

        logger.info(
            f"Ingestion complete: {stats.feeds_processed} feeds, "
            f"{stats.entries_new} new, {stats.entries_duplicate} duplicates"
        )

        return stats


def run_ingestion(config: Optional[ArgusConfig] = None) -> IngestionStats:
    """Convenience function to run RSS ingestion.

    Args:
        config: Optional config. Loads default if not provided.

    Returns:
        IngestionStats with results.
    """
    if config is None:
        config = ArgusConfig.load()

    worker = RSSWorker(config)
    try:
        return worker.run()
    finally:
        worker.close()
