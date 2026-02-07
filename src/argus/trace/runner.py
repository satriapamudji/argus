"""DB-free trace runner - orchestrates full pipeline execution.

Runs the complete pipeline: ingest → score → enrich → bundle → generate
and produces a detailed JSON trace without database access.
"""

import logging
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from argus.config import ArgusConfig
from argus.facts_bundle.types import FactsBundle
from argus.ingestion.rss_parser import parse_feed
from argus.ingestion.types import RSSEntry
from argus.scoring.types import ScoringCandidate, ScoringResult

from argus.trace.bundle_builder import (
    TraceBundleBuilder,
    TraceBundleConfig,
    rss_entry_to_scoring_candidate,
)
from argus.trace.types import (
    ScoredItemTrace,
    StageTrace,
    TraceOutput,
    create_stage_trace,
)

logger = logging.getLogger(__name__)


def run_trace(
    config: ArgusConfig,
    run_mode: str = "us_close",
    scoring_version: Optional[str] = None,
    trading_date: Optional[date] = None,
    skip_generate: bool = False,
) -> TraceOutput:
    """Run the full pipeline and produce a trace.

    This is the main entry point for the trace module. It executes:
    1. Ingest: Fetch RSS entries from configured feeds
    2. Score: Score all entries with the specified scoring version
    3. Enrich: (optional) Fetch full article content
    4. Bundle: Build FactsBundle with selection
    5. Generate: (optional) Generate message via LLM

    Args:
        config: Argus configuration.
        run_mode: Run mode (us_close, weekend_wrap, monday_preview, crypto_daily).
        scoring_version: Scoring version override (v2 or v3).
        trading_date: Trading date (defaults to today).
        skip_generate: If True, skip LLM generation step.

    Returns:
        TraceOutput with complete pipeline trace.
    """
    if trading_date is None:
        trading_date = date.today()

    # Determine scoring version
    if scoring_version is None:
        if config.stream.name == "crypto":
            scoring_version = "v3"
        else:
            scoring_version = "v2"

    # Initialize trace output
    run_id = str(uuid.uuid4())[:8]
    trace = TraceOutput(
        run_id=run_id,
        stream_name=config.stream.name,
        run_mode=run_mode,
        trading_date=trading_date.isoformat(),
        scoring_version=scoring_version,
        started_at=datetime.now(timezone.utc).isoformat(),
        completed_at=None,
    )

    logger.info(f"Starting trace run {run_id} for {config.stream.name}/{run_mode}")

    # Stage 1: Ingest RSS entries
    stage_start = datetime.now(timezone.utc)
    all_entries: list[tuple[RSSEntry, str]] = []  # (entry, feed_url)
    ingest_errors: list[str] = []

    feed_urls = _get_feed_urls(config)
    for feed_url in feed_urls:
        try:
            entries, error = parse_feed(feed_url)
            if error:
                ingest_errors.append(f"{feed_url}: {error}")
                continue
            for entry in entries:
                all_entries.append((entry, feed_url))
        except Exception as e:
            ingest_errors.append(f"{feed_url}: {e}")

    stage_end = datetime.now(timezone.utc)
    trace.add_stage(
        create_stage_trace(
            name="ingest",
            started_at=stage_start,
            completed_at=stage_end,
            item_count=len(all_entries),
            artifacts={"feed_count": len(feed_urls)},
            errors=ingest_errors,
        )
    )
    logger.info(f"Ingested {len(all_entries)} entries from {len(feed_urls)} feeds")

    if not all_entries:
        trace.errors.append("No entries ingested from any feed")
        trace.finalize()
        return trace

    # Stage 2: Score all entries
    stage_start = datetime.now(timezone.utc)
    scoring_results: list[tuple[ScoringResult, ScoringCandidate]] = []
    scoring_errors: list[str] = []

    # Convert entries to scoring candidates
    candidates: list[tuple[ScoringCandidate, str]] = []
    for entry, feed_url in all_entries:
        candidate = rss_entry_to_scoring_candidate(entry, feed_url)
        candidates.append((candidate, feed_url))

    # Score all candidates
    try:
        scored = _score_candidates(candidates, scoring_version, config)
        scoring_results = scored
    except Exception as e:
        scoring_errors.append(f"Scoring failed: {e}")
        logger.exception("Scoring failed")

    stage_end = datetime.now(timezone.utc)
    trace.add_stage(
        create_stage_trace(
            name="score",
            started_at=stage_start,
            completed_at=stage_end,
            item_count=len(scoring_results),
            artifacts={"scoring_version": scoring_version},
            errors=scoring_errors,
        )
    )
    logger.info(f"Scored {len(scoring_results)} candidates")

    # Record ALL scored items in trace
    selected_ids: set[int] = set()  # Will be populated after selection
    for result, candidate in scoring_results:
        breakdown_dict = None
        if result.breakdown:
            breakdown_dict = {
                "recency": result.breakdown.recency,
                "source_tier": result.breakdown.source_tier,
                "keyword_relevance": result.breakdown.keyword_relevance,
                "uniqueness": result.breakdown.uniqueness,
                "breaking_urgency": result.breakdown.breaking_urgency,
            }

        trace.all_scored_items.append(
            ScoredItemTrace(
                news_item_id=result.news_item_id,
                title=candidate.title,
                source_name=candidate.source_name,
                source_url=candidate.source_url,
                published_at=candidate.published_at.isoformat() if candidate.published_at else None,
                impact_score=result.impact_score,
                quality_score=result.quality_score,
                confidence_score=result.confidence_score,
                topic=result.topic,
                reasons=result.reasons,
                flags=result.flags,
                breakdown=breakdown_dict,
                selected_for_bundle=False,  # Will update after selection
            )
        )

    if not scoring_results:
        trace.errors.append("No items scored successfully")
        trace.finalize()
        return trace

    # Stage 3: Enrich (fetch article content) - simplified for trace
    # In trace mode, we skip enrichment to avoid slow HTTP fetches
    # The bundle builder will work with snippet-only content
    stage_start = datetime.now(timezone.utc)
    stage_end = datetime.now(timezone.utc)
    trace.add_stage(
        create_stage_trace(
            name="enrich",
            started_at=stage_start,
            completed_at=stage_end,
            item_count=0,
            artifacts={"skipped": True, "reason": "trace mode skips enrichment"},
        )
    )

    # Stage 4: Build FactsBundle
    stage_start = datetime.now(timezone.utc)
    bundle_errors: list[str] = []
    bundle: Optional[FactsBundle] = None

    try:
        builder_config = TraceBundleConfig.from_argus_config(config, run_mode, scoring_version)
        builder = TraceBundleBuilder(builder_config)
        bundle, stats = builder.build(scoring_results, trading_date)

        # Mark selected items in trace
        selected_ids = {item.id for item in bundle.news_items}
        for scored_item in trace.all_scored_items:
            if scored_item.news_item_id in selected_ids:
                scored_item.selected_for_bundle = True

        trace.set_bundle(bundle)

    except Exception as e:
        bundle_errors.append(f"Bundle build failed: {e}")
        logger.exception("Bundle build failed")

    stage_end = datetime.now(timezone.utc)
    trace.add_stage(
        create_stage_trace(
            name="bundle",
            started_at=stage_start,
            completed_at=stage_end,
            item_count=len(selected_ids),
            artifacts={
                "total_candidates": len(scoring_results),
                "selected": len(selected_ids),
            },
            errors=bundle_errors,
        )
    )

    if bundle is None:
        trace.errors.append("Failed to build facts bundle")
        trace.finalize()
        return trace

    # Stage 5: Generate message (optional)
    if not skip_generate:
        stage_start = datetime.now(timezone.utc)
        generate_errors: list[str] = []
        message: Optional[str] = None

        try:
            message = _generate_message(bundle, config)
            trace.generated_message = message
        except Exception as e:
            generate_errors.append(f"Generation failed: {e}")
            logger.exception("Generation failed")

        stage_end = datetime.now(timezone.utc)
        trace.add_stage(
            create_stage_trace(
                name="generate",
                started_at=stage_start,
                completed_at=stage_end,
                item_count=1 if message else 0,
                errors=generate_errors,
            )
        )
    else:
        logger.info("Skipping generation (--skip-generate)")

    trace.finalize()
    logger.info(f"Trace run {run_id} completed")
    return trace


def _get_feed_urls(config: ArgusConfig) -> list[str]:
    """Get all feed URLs from config."""
    urls: list[str] = []

    # Load from allowlist files
    allowlist_files = config.stream.rss.allowlist_files or []
    for allowlist_file in allowlist_files:
        path = Path(allowlist_file)
        if path.exists():
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        urls.append(line)

    return list(set(urls))  # Deduplicate


def _score_candidates(
    candidates: list[tuple[ScoringCandidate, str]],
    scoring_version: str,
    config: ArgusConfig,
) -> list[tuple[ScoringResult, ScoringCandidate]]:
    """Score candidates using the specified scoring version.

    Args:
        candidates: List of (ScoringCandidate, feed_url) tuples.
        scoring_version: v2 or v3.
        config: Argus configuration (provides ScoringConfig).

    Returns:
        List of (ScoringResult, ScoringCandidate) tuples.
    """
    # Extract just the candidates
    scoring_candidates = [c for c, _ in candidates]
    scoring_config = config.stream.scoring

    if scoring_version == "v3":
        from argus.scoring.heuristics_v3 import score_candidates_v3

        results = score_candidates_v3(scoring_candidates, scoring_config)
    else:
        from argus.scoring.heuristics_v2 import score_candidates_v2

        results = score_candidates_v2(scoring_candidates, scoring_config)

    # Map results back to candidates
    result_map = {r.news_item_id: r for r in results}
    paired: list[tuple[ScoringResult, ScoringCandidate]] = []

    for candidate, _ in candidates:
        if candidate.news_item_id in result_map:
            paired.append((result_map[candidate.news_item_id], candidate))

    return paired


def _generate_message(bundle: FactsBundle, config: ArgusConfig) -> str:
    """Generate message from bundle using LLM.

    Args:
        bundle: The facts bundle.
        config: Argus configuration.

    Returns:
        Generated message string.
    """
    from argus.generator.generator import MessageGenerator

    generator = MessageGenerator(
        config=config.stream.generator,
        constraints=config.stream.constraints,
    )

    result, validation = generator.generate(bundle)
    return result.message
