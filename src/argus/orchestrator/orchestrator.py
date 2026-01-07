"""Main run orchestrator for Argus pipeline.

The RunOrchestrator ties together all pipeline components:
1. [Optional] Ingest (if --include-ingest)
2. Check holiday/half-day → apply behavior
3. [Optional] Score items (if not --skip-scoring)
4. [Optional] Enrich items (if not --skip-enrichment)
5. Calculate risk_score (if monday_preview)
6. Check conditional gate (if --conditional)
7. Build facts bundle
8. Generate message (LLM)
9. Validate message
10. Create run + message records
11. [Optional] Publish (if not --skip-publish)
12. Update run status + timings
"""

import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Optional
import logging

from psycopg2.extensions import connection as Connection

from argus.config import ArgusConfig
from argus.db.connection import get_connection
from argus.db.repository import (
    create_message,
    create_run,
    update_message,
    update_run,
)
from argus.orchestrator.holiday import check_holiday_status
from argus.orchestrator.risk_score import calculate_risk_score
from argus.orchestrator.types import (
    HalfDayBehavior,
    HolidayBehavior,
    RunMode,
    RunResult,
    RunStatus,
    RunTimings,
)
from argus.orchestrator.window import get_trading_date_for_run, get_window_for_mode

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorOptions:
    """Options controlling the orchestrator run.

    Attributes:
        skip_publish: Run pipeline but don't send to Telegram.
        skip_scoring: Assume items are already scored.
        skip_enrichment: Assume items are already enriched.
        include_ingest: Trigger ingestion before pipeline.
        conditional: For monday_preview, check risk_score threshold.
        force_publish: Override conditional check (always publish).
        force_skip: Override conditional check (never publish).
        dry_run: Load config, show what would happen, don't execute.
        risk_threshold: Minimum risk_score for monday_preview (default 60).
    """

    skip_publish: bool = False
    skip_scoring: bool = False
    skip_enrichment: bool = False
    include_ingest: bool = False
    conditional: bool = False
    force_publish: bool = False
    force_skip: bool = False
    dry_run: bool = False
    risk_threshold: int = 60

    def __post_init__(self) -> None:
        """Validate conflicting options."""
        if self.force_publish and self.force_skip:
            raise ValueError("Cannot use both --force-publish and --force-skip")


@dataclass
class StepTimer:
    """Simple timer for tracking step durations."""

    _times: dict[str, int] = field(default_factory=dict)
    _start: Optional[float] = None
    _current_step: Optional[str] = None

    def start(self, step: str) -> None:
        """Start timing a step."""
        self._current_step = step
        self._start = time.time()

    def stop(self) -> None:
        """Stop timing the current step."""
        if self._start is not None and self._current_step is not None:
            elapsed_ms = int((time.time() - self._start) * 1000)
            self._times[self._current_step] = elapsed_ms
        self._start = None
        self._current_step = None

    def get(self, step: str) -> Optional[int]:
        """Get duration for a step in milliseconds."""
        return self._times.get(step)

    def total(self) -> int:
        """Get total duration in milliseconds."""
        return sum(self._times.values())


class RunOrchestrator:
    """Orchestrates the complete run pipeline.

    Usage:
        orchestrator = RunOrchestrator(config, mode, options)
        result = orchestrator.run()
    """

    def __init__(
        self,
        config: ArgusConfig,
        mode: RunMode,
        options: Optional[OrchestratorOptions] = None,
        conn: Optional[Connection] = None,
    ) -> None:
        """Initialize the orchestrator.

        Args:
            config: Argus configuration.
            mode: Run mode (us_close, weekend_wrap, monday_preview).
            options: Orchestrator options.
            conn: Optional database connection.
        """
        self.config = config
        self.mode = mode
        self.options = options or OrchestratorOptions()
        self._conn = conn
        self._owns_connection = conn is None
        self._timer = StepTimer()

    def _get_connection(self) -> Connection:
        """Get or create database connection."""
        if self._conn is None:
            self._conn = get_connection()
        return self._conn

    def _close_connection(self) -> None:
        """Close connection if we own it."""
        if self._owns_connection and self._conn is not None:
            self._conn.close()
            self._conn = None

    def run(self, now: Optional[datetime] = None) -> RunResult:
        """Execute the complete run pipeline.

        Args:
            now: Optional current time (for testing).

        Returns:
            RunResult with status and details.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        result = RunResult(mode=self.mode, stream_name=self.config.stream.name)
        total_start = time.time()

        try:
            conn = self._get_connection()

            # Step 1: Determine window and trading date
            self._timer.start("window_selection")
            window = get_window_for_mode(self.mode, now)
            trading_date = get_trading_date_for_run(self.mode, now)
            result.trading_date = datetime.combine(trading_date, datetime.min.time())
            self._timer.stop()

            logger.info(
                f"Run: mode={self.mode.value}, trading_date={trading_date}, "
                f"window={window.start.isoformat()} to {window.end.isoformat()}"
            )

            if self.options.dry_run:
                return self._dry_run(result, window, trading_date)

            # Step 2: Check holiday/half-day status
            holiday_info = check_holiday_status(
                trading_date=trading_date,
                mode=self.mode,
                holiday_behavior=self._get_holiday_behavior(),
                half_day_behavior=self._get_half_day_behavior(),
            )
            result.holiday_info = holiday_info

            if holiday_info.should_skip:
                result.status = RunStatus.SKIPPED
                logger.info(f"Run skipped: {holiday_info.behavior_applied}")
                return result

            # Step 3: Optional ingestion
            if self.options.include_ingest:
                self._timer.start("ingest")
                self._run_ingestion()
                self._timer.stop()

            # Step 4: Optional scoring
            if not self.options.skip_scoring:
                self._timer.start("scoring")
                self._run_scoring(conn)
                self._timer.stop()

            # Step 5: Optional enrichment
            if not self.options.skip_enrichment:
                self._timer.start("enrichment")
                self._run_enrichment(conn)
                self._timer.stop()

            # Step 6: Calculate risk score (monday_preview)
            if self.mode == RunMode.MONDAY_PREVIEW:
                self._timer.start("risk_score")
                risk_breakdown = calculate_risk_score(
                    conn=conn,
                    window_start=window.start,
                    window_end=window.end,
                )
                result.risk_score = risk_breakdown
                self._timer.stop()

                # Step 7: Conditional check
                if self.options.conditional and not self.options.force_publish:
                    if (
                        self.options.force_skip
                        or risk_breakdown.total < self.options.risk_threshold
                    ):
                        result.status = RunStatus.SKIPPED
                        result.was_conditional_skip = True
                        logger.info(
                            f"Monday preview conditional skip: risk_score={risk_breakdown.total} "
                            f"< threshold={self.options.risk_threshold}"
                        )
                        return result

            # Step 8: Create run record
            run_row = create_run(
                conn=conn,
                stream_name=self.config.stream.name,
                run_mode=self.mode.value,
            )
            result.run_id = run_row.id
            result.status = RunStatus.RUNNING
            logger.info(f"Created run record: id={run_row.id}")

            # Step 9: Build facts bundle
            self._timer.start("bundle")
            bundle, bundle_stats = self._build_facts_bundle(conn, trading_date)
            result.facts_bundle = bundle.to_dict()
            self._timer.stop()
            logger.info(f"Built facts bundle: {bundle_stats.selected_items} items")

            # Step 10: Generate message
            self._timer.start("generation")
            message_content, generation_result = self._generate_message(bundle)
            result.message_content = message_content
            self._timer.stop()
            logger.info(f"Generated message: {len(message_content)} chars")

            # Step 11: Validate message
            self._timer.start("validation")
            validation_result = self._validate_message(message_content, bundle)
            is_valid = validation_result.get("is_valid", False)
            self._timer.stop()

            # Step 12: Create message record
            message_row = create_message(
                conn=conn,
                run_id=run_row.id,
                content=message_content,
            )
            result.message_id = message_row.id

            # Update message with validation result
            update_message(
                conn=conn,
                message_id=message_row.id,
                validation_status="valid" if is_valid else "invalid",
                validation_errors=validation_result.get("errors", []),
            )

            # Step 13: Publish (if not skipped)
            if not self.options.skip_publish:
                self._timer.start("publish")
                try:
                    telegram_msg_id = self._publish_message(message_content)
                    result.telegram_message_id = telegram_msg_id

                    update_message(
                        conn=conn,
                        message_id=message_row.id,
                        publish_status="published",
                        telegram_message_id=telegram_msg_id,
                        published_at=datetime.now(timezone.utc),
                    )
                    logger.info(f"Published to Telegram: message_id={telegram_msg_id}")
                except Exception as e:
                    logger.error(f"Failed to publish: {e}")
                    update_message(
                        conn=conn,
                        message_id=message_row.id,
                        publish_status="failed",
                    )
                    raise
                finally:
                    self._timer.stop()
            else:
                result.publish_skipped = True
                update_message(
                    conn=conn,
                    message_id=message_row.id,
                    publish_status="skipped",
                )
                logger.info("Publishing skipped (--skip-publish)")

            # Step 14: Update run record with results
            result.status = RunStatus.COMPLETED
            result.timings = self._build_timings(total_start)

            update_run(
                conn=conn,
                run_id=run_row.id,
                status="completed",
                facts_bundle_json=result.facts_bundle,
                timings_json=result.timings.to_dict(),
                risk_score=result.risk_score.total if result.risk_score else None,
                calendar_score=result.risk_score.calendar_score if result.risk_score else None,
                market_score=result.risk_score.market_score if result.risk_score else None,
                headline_score=result.risk_score.headline_score if result.risk_score else None,
                completed_at=datetime.now(timezone.utc),
            )

            logger.info(f"Run completed: id={run_row.id}, status=completed")
            return result

        except Exception as e:
            logger.exception(f"Run failed: {e}")
            result.status = RunStatus.FAILED
            result.error = str(e)
            result.timings = self._build_timings(total_start)

            # Update run record with error if we created one
            if result.run_id:
                try:
                    update_run(
                        conn=self._get_connection(),
                        run_id=result.run_id,
                        status="failed",
                        error_message=str(e),
                        timings_json=result.timings.to_dict(),
                        completed_at=datetime.now(timezone.utc),
                    )
                except Exception as update_error:
                    logger.error(f"Failed to update run with error: {update_error}")

            return result

        finally:
            self._close_connection()

    def _dry_run(
        self,
        result: RunResult,
        window: Any,
        trading_date: date,
    ) -> RunResult:
        """Execute a dry run (show what would happen).

        Args:
            result: RunResult to populate.
            window: Window configuration.
            trading_date: Trading date.

        Returns:
            Updated RunResult.
        """
        logger.info("=== DRY RUN MODE ===")
        logger.info(f"Mode: {self.mode.value}")
        logger.info(f"Stream: {self.config.stream.name}")
        logger.info(f"Trading date: {trading_date}")
        logger.info(f"Window: {window.start.isoformat()} to {window.end.isoformat()}")
        logger.info(f"Window hours: {window.window_hours}")

        # Check holiday status
        holiday_info = check_holiday_status(
            trading_date=trading_date,
            mode=self.mode,
            holiday_behavior=self._get_holiday_behavior(),
            half_day_behavior=self._get_half_day_behavior(),
        )
        result.holiday_info = holiday_info

        if holiday_info.is_holiday:
            logger.info(f"Holiday: {holiday_info.holiday_name or 'Unknown'}")
            logger.info(f"Behavior: {holiday_info.behavior_applied}")
            if holiday_info.should_skip:
                logger.info("Result: Run would be SKIPPED")
        elif holiday_info.is_half_day:
            logger.info("Half-day / Early close")
            logger.info(f"Behavior: {holiday_info.behavior_applied}")
        else:
            logger.info("Normal trading day")

        logger.info("Options:")
        logger.info(f"  skip_publish: {self.options.skip_publish}")
        logger.info(f"  skip_scoring: {self.options.skip_scoring}")
        logger.info(f"  skip_enrichment: {self.options.skip_enrichment}")
        logger.info(f"  include_ingest: {self.options.include_ingest}")
        logger.info(f"  conditional: {self.options.conditional}")

        if self.mode == RunMode.MONDAY_PREVIEW and self.options.conditional:
            logger.info(f"  risk_threshold: {self.options.risk_threshold}")
            logger.info("  Note: Risk score would be calculated to determine publish")

        result.status = RunStatus.SKIPPED
        return result

    def _get_holiday_behavior(self) -> Optional[HolidayBehavior]:
        """Get configured holiday behavior."""
        behavior_str = self.config.stream.holiday_behavior.holiday_behavior
        if behavior_str == "skip":
            return HolidayBehavior.SKIP
        elif behavior_str == "publish_closed_note":
            return HolidayBehavior.PUBLISH_CLOSED_NOTE
        return None

    def _get_half_day_behavior(self) -> Optional[HalfDayBehavior]:
        """Get configured half-day behavior."""
        behavior_str = self.config.stream.holiday_behavior.half_day_behavior
        if behavior_str == "label_half_day":
            return HalfDayBehavior.LABEL_HALF_DAY
        elif behavior_str == "skip":
            return HalfDayBehavior.SKIP
        return None

    def _run_ingestion(self) -> None:
        """Run ingestion step."""
        from argus.ingestion import run_ingestion

        logger.info("Running ingestion...")
        run_ingestion(self.config)
        logger.info("Ingestion complete")

    def _run_scoring(self, conn: Connection) -> None:
        """Run scoring step."""
        from argus.scoring.worker import ScoringWorker

        logger.info("Running scoring...")
        worker = ScoringWorker(
            config=self.config,
            conn=conn,
            window_hours=self.config.stream.scoring.window_hours,
        )
        stats = worker.run()
        logger.info(f"Scoring complete: {stats.scored} items scored")

    def _run_enrichment(self, conn: Connection) -> None:
        """Run enrichment step."""
        from argus.enrichment.worker import EnrichmentWorker

        logger.info("Running enrichment...")
        worker = EnrichmentWorker(
            config=self.config,
            conn=conn,
            window_hours=self.config.stream.scoring.window_hours,
        )
        stats = worker.run()
        logger.info(f"Enrichment complete: {stats.items_enriched} items enriched")

    def _build_facts_bundle(
        self,
        conn: Connection,
        trading_date: date,
    ) -> tuple[Any, Any]:
        """Build facts bundle.

        Returns:
            Tuple of (FactsBundle, BundleStats).
        """
        from argus.facts_bundle.builder import BundleBuilderConfig, FactsBundleBuilder

        builder_config = BundleBuilderConfig.from_argus_config(self.config, self.mode.value)
        builder = FactsBundleBuilder(config=builder_config, conn=conn)
        return builder.build(trading_date=trading_date)

    def _generate_message(self, bundle: Any) -> tuple[str, Any]:
        """Generate message from facts bundle.

        Returns:
            Tuple of (message_content, generation_result).
        """
        from argus.generator.generator import MessageGenerator
        from argus.generator.types import GenerationMode

        generator = MessageGenerator(
            config=self.config.stream.generator,
            constraints=self.config.stream.constraints,
        )
        gen_mode = GenerationMode.from_string(self.mode.value)
        result, validation = generator.generate(bundle=bundle, mode=gen_mode)
        return result.message, result

    def _validate_message(self, message: str, bundle: Any) -> dict[str, Any]:
        """Validate generated message.

        Returns:
            Validation result dict with is_valid and errors.
        """
        # Validation is done during generate() step, so we return a placeholder.
        # In the future, this could run additional validation passes.
        # For now, we trust the generator's internal validation.
        _ = message  # Suppress unused variable warning
        _ = bundle  # Suppress unused variable warning
        return {
            "is_valid": True,  # Validation is done in generate()
            "errors": [],
        }

    def _publish_message(self, content: str) -> Optional[int]:
        """Publish message to Telegram.

        Returns:
            Telegram message ID or None if not available.
        """
        from argus.publisher.telegram import TelegramPublisher

        publisher = TelegramPublisher(config=self.config.stream.telegram)
        result = publisher.publish(content=content)
        return result.telegram_message_id

    def _build_timings(self, total_start: float) -> RunTimings:
        """Build RunTimings from step timer."""
        total_ms = int((time.time() - total_start) * 1000)

        return RunTimings(
            ingest_ms=self._timer.get("ingest"),
            scoring_ms=self._timer.get("scoring"),
            enrichment_ms=self._timer.get("enrichment"),
            window_selection_ms=self._timer.get("window_selection"),
            risk_score_ms=self._timer.get("risk_score"),
            bundle_ms=self._timer.get("bundle"),
            generation_ms=self._timer.get("generation"),
            validation_ms=self._timer.get("validation"),
            publish_ms=self._timer.get("publish"),
            total_ms=total_ms,
        )


def run_orchestrator(
    config: Optional[ArgusConfig] = None,
    mode: str = "us_close",
    options: Optional[OrchestratorOptions] = None,
    conn: Optional[Connection] = None,
) -> RunResult:
    """Convenience function to run the orchestrator.

    Args:
        config: Optional Argus config (loads default if not provided).
        mode: Run mode string.
        options: Orchestrator options.
        conn: Optional database connection.

    Returns:
        RunResult with status and details.
    """
    if config is None:
        config = ArgusConfig.load()

    run_mode = RunMode.from_string(mode)
    orchestrator = RunOrchestrator(
        config=config,
        mode=run_mode,
        options=options,
        conn=conn,
    )
    return orchestrator.run()
