"""Enrichment worker for Argus.

Orchestrates content fetching and enrichment for top-scored news items.
"""

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Optional

from psycopg2.extensions import connection as Connection

from argus.config import ArgusConfig, EnrichmentConfig
from argus.db.connection import get_connection
from argus.enrichment.extractor import truncate_to_excerpt
from argus.enrichment.extractors import get_extractor
from argus.enrichment.fetcher import AsyncContentFetcher
from argus.enrichment.types import EnrichmentCandidate, EnrichmentResult

logger = logging.getLogger(__name__)


@dataclass
class EnrichmentStats:
    """Statistics from an enrichment run."""

    candidates_found: int = 0
    items_enriched: int = 0
    items_failed: int = 0
    items_skipped: int = 0  # Already enriched
    total_content_chars: int = 0
    errors: list[str] = field(default_factory=list)


class EnrichmentWorker:
    """Content enrichment worker.

    Fetches and stores article content for top-scored news items.
    Designed to be run after scoring, before LLM triage.
    """

    def __init__(
        self,
        config: ArgusConfig,
        conn: Optional[Connection] = None,
        window_hours: int = 24,
    ) -> None:
        """Initialize the enrichment worker.

        Args:
            config: Argus configuration.
            conn: Optional database connection. If not provided, creates one.
            window_hours: Look back window for candidates (default 24 hours).
        """
        self.config = config
        self.enrichment_config: EnrichmentConfig = config.stream.enrichment
        self._conn = conn
        self._owns_connection = conn is None
        self.window_hours = window_hours

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

    def _get_candidates(self) -> list[EnrichmentCandidate]:
        """Get news items eligible for enrichment.

        Selects top K items by impact_score that don't already have content.
        """
        limit = self.enrichment_config.max_enrich_per_run

        query = """
            SELECT ni.id, ni.source_url, ni.title, ni.ingested_at, ns.impact_score
            FROM news_items ni
            JOIN news_scores ns ON ni.id = ns.news_item_id
            LEFT JOIN news_content nc ON ni.id = nc.news_item_id
            WHERE ni.ingested_at >= NOW() - INTERVAL '%s hours'
              AND nc.id IS NULL
            ORDER BY ns.impact_score DESC
            LIMIT %s
        """

        with self.conn.cursor() as cur:
            cur.execute(query, (self.window_hours, limit))
            rows = cur.fetchall()

        return [EnrichmentCandidate.from_row(row) for row in rows]

    def _has_content(self, news_item_id: int) -> bool:
        """Check if a news item already has content stored."""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM news_content WHERE news_item_id = %s LIMIT 1",
                (news_item_id,),
            )
            return cur.fetchone() is not None

    def _insert_content(
        self,
        news_item_id: int,
        ingested_at: object,
        content_type: str,
        content: str,
        status: str = "success",
    ) -> None:
        """Insert content into news_content table."""
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO news_content 
                    (news_item_id, ingested_at, content_type, content, content_hash, content_status)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (news_item_id, ingested_at, content_type, content, content_hash, status),
            )
        self.conn.commit()

    def _insert_failed_content(
        self,
        news_item_id: int,
        ingested_at: object,
        error: str,
    ) -> None:
        """Insert a failed content record."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO news_content 
                    (news_item_id, ingested_at, content_type, content, content_hash, content_status)
                VALUES (%s, %s, 'excerpt', %s, %s, 'failed')
                """,
                (
                    news_item_id,
                    ingested_at,
                    f"[Fetch failed: {error}]",
                    hashlib.sha256(error.encode()).hexdigest(),
                ),
            )
        self.conn.commit()

    def _update_news_item_metadata(
        self,
        news_item_id: int,
        ingested_at: object,
        author: str | None,
        published_at: object | None,
    ) -> None:
        """Update news_items with better metadata from page extraction.

        Always overwrites existing values when page extraction provides data.
        Uses ingested_at for partitioned table query optimization.

        Args:
            news_item_id: The news item ID.
            ingested_at: Ingestion timestamp (for partition pruning).
            author: Extracted author name (or None to skip).
            published_at: Extracted publication datetime (or None to skip).
        """
        if not author and not published_at:
            return

        # Build dynamic SET clause based on what we have
        set_parts = []
        params: list[object] = []

        if author:
            set_parts.append("author = %s")
            params.append(author)

        if published_at:
            set_parts.append("published_at = %s")
            params.append(published_at)

        # Add WHERE params
        params.extend([news_item_id, ingested_at])

        query = f"""
            UPDATE news_items
            SET {", ".join(set_parts)}
            WHERE id = %s AND ingested_at = %s
        """

        with self.conn.cursor() as cur:
            cur.execute(query, params)
        self.conn.commit()

    async def _enrich_candidate(
        self,
        candidate: EnrichmentCandidate,
        fetcher: AsyncContentFetcher,
    ) -> EnrichmentResult:
        """Enrich a single candidate.

        Args:
            candidate: The news item to enrich.
            fetcher: Async HTTP fetcher.

        Returns:
            EnrichmentResult with success/failure info.
        """
        # Double-check not already enriched (race condition protection)
        if self._has_content(candidate.id):
            return EnrichmentResult(
                news_item_id=candidate.id,
                success=False,
                error="Already enriched",
            )

        # Fetch content
        fetch_result = await fetcher.fetch(candidate.source_url)

        if not fetch_result.success:
            self._insert_failed_content(
                candidate.id,
                candidate.ingested_at,
                fetch_result.error or "Unknown fetch error",
            )
            return EnrichmentResult(
                news_item_id=candidate.id,
                success=False,
                error=fetch_result.error,
            )

        # Extract text from HTML using source-specific extractor
        extractor = get_extractor(candidate.source_url)
        extracted = extractor.extract(fetch_result.html or "", candidate.source_url)

        if not extracted or not extracted.content:
            self._insert_failed_content(
                candidate.id,
                candidate.ingested_at,
                "Failed to extract text",
            )
            return EnrichmentResult(
                news_item_id=candidate.id,
                success=False,
                error="Failed to extract text",
            )

        # Update news_items metadata if extractor found better values
        if extracted.author or extracted.published_at:
            self._update_news_item_metadata(
                candidate.id,
                candidate.ingested_at,
                extracted.author,
                extracted.published_at,
            )

        # Determine content type and truncate if needed
        if self.enrichment_config.allow_full_text_storage:
            content_type = "full_text"
            content = extracted.content
        else:
            content_type = "excerpt"
            content = truncate_to_excerpt(extracted.content, self.enrichment_config.snippet_chars)

        # Store content
        self._insert_content(
            candidate.id,
            candidate.ingested_at,
            content_type,
            content,
        )

        logger.info(f"Enriched: {candidate.title[:50]}... ({len(content)} chars)")

        return EnrichmentResult(
            news_item_id=candidate.id,
            success=True,
            content_type=content_type,
            content_length=len(content),
        )

    async def _run_async(self) -> EnrichmentStats:
        """Async implementation of enrichment run."""
        stats = EnrichmentStats()

        if not self.enrichment_config.enabled:
            logger.info("Enrichment is disabled")
            return stats

        # Get candidates
        candidates = self._get_candidates()
        stats.candidates_found = len(candidates)

        if not candidates:
            logger.info("No candidates for enrichment")
            return stats

        logger.info(f"Found {len(candidates)} candidates for enrichment")

        # Fetch and enrich
        async with AsyncContentFetcher() as fetcher:
            for candidate in candidates:
                try:
                    result = await self._enrich_candidate(candidate, fetcher)

                    if result.success:
                        stats.items_enriched += 1
                        stats.total_content_chars += result.content_length
                    elif result.error == "Already enriched":
                        stats.items_skipped += 1
                    else:
                        stats.items_failed += 1
                        if result.error:
                            stats.errors.append(f"{candidate.source_url}: {result.error}")

                except Exception as e:
                    stats.items_failed += 1
                    stats.errors.append(f"{candidate.source_url}: {e}")
                    logger.exception(f"Error enriching {candidate.source_url}")

        logger.info(
            f"Enrichment complete: {stats.items_enriched} enriched, "
            f"{stats.items_failed} failed, {stats.items_skipped} skipped"
        )

        return stats

    def run(self) -> EnrichmentStats:
        """Run enrichment for top-scored items.

        Returns:
            EnrichmentStats with results.
        """
        return asyncio.run(self._run_async())


def run_enrichment(
    config: Optional[ArgusConfig] = None,
    window_hours: int = 24,
) -> EnrichmentStats:
    """Convenience function to run content enrichment.

    Args:
        config: Optional config. Loads default if not provided.
        window_hours: Look back window for candidates.

    Returns:
        EnrichmentStats with results.
    """
    if config is None:
        config = ArgusConfig.load()

    worker = EnrichmentWorker(config, window_hours=window_hours)
    try:
        return worker.run()
    finally:
        worker.close()
