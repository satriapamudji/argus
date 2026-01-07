"""Scoring worker for Argus.

Orchestrates the scoring pipeline:
1. Get unscored news items from the window
2. Apply heuristic scoring
3. Optionally apply LLM triage
4. Store scores in the database
"""

import logging
import time
from typing import Optional

from psycopg2.extensions import connection as Connection

from argus.config import ArgusConfig, ScoringConfig
from argus.db.connection import get_connection
from argus.scoring.heuristics import HeuristicScorer
from argus.scoring.llm_triage import apply_llm_triage
from argus.scoring.types import ScoringCandidate, ScoringResult, ScoringStats

logger = logging.getLogger(__name__)


class ScoringWorker:
    """News item scoring worker.

    Scores new items using heuristics and optional LLM triage,
    then stores the results in the news_scores table.
    """

    def __init__(
        self,
        config: ArgusConfig,
        conn: Optional[Connection] = None,
        window_hours: Optional[int] = None,
        dry_run: bool = False,
    ) -> None:
        """Initialize the scoring worker.

        Args:
            config: Argus configuration.
            conn: Optional database connection. If not provided, creates one.
            window_hours: Look back window in hours. Defaults to config value.
            dry_run: If True, don't write to database.
        """
        self.config = config
        self.scoring_config: ScoringConfig = config.stream.scoring
        self._conn = conn
        self._owns_connection = conn is None
        self.window_hours = window_hours or self.scoring_config.window_hours
        self.dry_run = dry_run

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

    def _get_candidates(self) -> list[ScoringCandidate]:
        """Get news items eligible for scoring.

        Returns items from the window that don't already have scores.
        """
        limit = self.scoring_config.max_items_per_run

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
            JOIN news_fingerprints nf ON ni.fingerprint_id = nf.id
            LEFT JOIN news_scores ns ON ni.id = ns.news_item_id
            WHERE ni.ingested_at >= NOW() - INTERVAL '%s hours'
              AND ns.id IS NULL
            ORDER BY ni.ingested_at DESC
            LIMIT %s
        """

        with self.conn.cursor() as cur:
            cur.execute(query, (self.window_hours, limit))
            rows = cur.fetchall()

        return [
            ScoringCandidate(
                news_item_id=row[0],
                fingerprint_id=row[1],
                source_name=row[2],
                source_url=row[3],
                title=row[4],
                snippet=row[5],
                published_at=row[6],
                ingested_at=row[7],
                simhash=row[8],
            )
            for row in rows
        ]

    def _get_recent_simhashes(self) -> list[int]:
        """Get SimHashes from recent items for uniqueness comparison.

        Returns SimHashes from ALL recent items, including already-scored ones.
        This allows new items to be compared against the full history.
        """
        query = """
            SELECT DISTINCT nf.simhash
            FROM news_fingerprints nf
            JOIN news_items ni ON nf.id = ni.fingerprint_id
            WHERE ni.ingested_at >= NOW() - INTERVAL '%s hours'
              AND nf.simhash IS NOT NULL
        """

        with self.conn.cursor() as cur:
            cur.execute(query, (self.window_hours,))
            rows = cur.fetchall()

        return [row[0] for row in rows if row[0] is not None]

    def _has_score(self, news_item_id: int) -> bool:
        """Check if a news item already has a score."""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM news_scores WHERE news_item_id = %s LIMIT 1",
                (news_item_id,),
            )
            return cur.fetchone() is not None

    def _insert_score(self, result: ScoringResult) -> int:
        """Insert a score into the news_scores table.

        Args:
            result: The scoring result to insert.

        Returns:
            ID of the inserted row.
        """
        import json

        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO news_scores 
                    (news_item_id, ingested_at, impact_score, quality_score, 
                     confidence_score, topic, flags, reasons, scorer_version)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    result.news_item_id,
                    result.ingested_at,
                    result.impact_score,
                    result.quality_score,
                    result.confidence_score,
                    result.topic,
                    json.dumps(result.flags) if result.flags else None,
                    json.dumps(result.reasons) if result.reasons else None,
                    result.scorer_version,
                ),
            )
            row = cur.fetchone()
            self.conn.commit()

            if row:
                return row[0]
            raise RuntimeError("Failed to insert news score")

    def run(self) -> ScoringStats:
        """Run the scoring pipeline.

        Returns:
            ScoringStats with results.
        """
        start_time = time.time()
        stats = ScoringStats()

        if not self.scoring_config.enabled:
            logger.info("Scoring is disabled")
            return stats

        # Get candidates
        candidates = self._get_candidates()
        stats.total_candidates = len(candidates)

        if not candidates:
            logger.info("No candidates for scoring")
            return stats

        logger.info(f"Found {len(candidates)} candidates for scoring")

        # Get recent SimHashes for uniqueness comparison
        recent_simhashes = self._get_recent_simhashes()
        logger.debug(f"Loaded {len(recent_simhashes)} recent SimHashes for comparison")

        # Create scorer and score candidates
        scorer = HeuristicScorer(self.scoring_config)
        scorer.set_recent_simhashes(recent_simhashes)

        results: list[ScoringResult] = []
        for candidate in candidates:
            try:
                result = scorer.score_candidate(candidate)
                results.append(result)
            except Exception as e:
                logger.warning(f"Error scoring item {candidate.news_item_id}: {e}")
                stats.errors += 1

        # Sort by impact score descending
        results.sort(key=lambda r: r.impact_score, reverse=True)

        # Apply LLM triage if enabled
        if self.scoring_config.llm_triage_enabled:
            try:
                results = apply_llm_triage(results, candidates, self.scoring_config)
                stats.llm_triaged = sum(1 for r in results if "llm_triaged" in r.flags)
                logger.info(f"LLM triage applied to {stats.llm_triaged} items")
            except Exception as e:
                logger.warning(f"LLM triage failed: {e}")

        # Store results
        for result in results:
            try:
                # Double-check not already scored (race condition protection)
                if self._has_score(result.news_item_id):
                    stats.skipped_already_scored += 1
                    continue

                if not self.dry_run:
                    self._insert_score(result)

                stats.scored += 1

                if stats.scored <= 5:
                    # Log top 5 items
                    logger.info(
                        f"Scored: {result.impact_score:3d} pts - "
                        f"{result.topic or 'unknown':12s} - "
                        f"{candidates[0].title[:50] if candidates else 'N/A'}..."
                    )

            except Exception as e:
                logger.warning(f"Error storing score for {result.news_item_id}: {e}")
                stats.errors += 1

        stats.duration_seconds = time.time() - start_time

        logger.info(
            f"Scoring complete: {stats.scored} scored, "
            f"{stats.skipped_already_scored} skipped, "
            f"{stats.errors} errors in {stats.duration_seconds:.1f}s"
        )

        if self.dry_run:
            logger.info("DRY RUN - no scores were written to database")
            self._log_dry_run_summary(results, candidates)

        return stats

    def _log_dry_run_summary(
        self,
        results: list[ScoringResult],
        candidates: list[ScoringCandidate],
    ) -> None:
        """Log a summary of what would be written in dry-run mode."""
        candidate_map = {c.news_item_id: c for c in candidates}

        logger.info("\n=== DRY RUN SUMMARY ===")
        logger.info(f"Top {min(10, len(results))} items by score:\n")

        for i, result in enumerate(results[:10], 1):
            candidate = candidate_map.get(result.news_item_id)
            title = candidate.title[:60] if candidate else "Unknown"
            source = candidate.source_name if candidate else "Unknown"

            logger.info(
                f"{i:2d}. [{result.impact_score:3d}] {result.topic or 'other':12s} "
                f"| {source:15s} | {title}..."
            )
            if result.flags:
                logger.info(f"    Flags: {', '.join(result.flags)}")
            logger.info(f"    Reasons: {', '.join(result.reasons[:3])}")


def run_scoring(
    config: Optional[ArgusConfig] = None,
    window_hours: Optional[int] = None,
    dry_run: bool = False,
) -> ScoringStats:
    """Convenience function to run scoring.

    Args:
        config: Optional config. Loads default if not provided.
        window_hours: Look back window in hours.
        dry_run: If True, don't write to database.

    Returns:
        ScoringStats with results.
    """
    if config is None:
        config = ArgusConfig.load()

    worker = ScoringWorker(config, window_hours=window_hours, dry_run=dry_run)
    try:
        return worker.run()
    finally:
        worker.close()
