"""Main daemon scheduler for Argus.

Provides a long-running daemon with internal scheduling using APScheduler.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from argus import __version__
from argus.config import ArgusConfig
from argus.daemon.health import HealthServer
from argus.daemon.persistence import (
    cleanup_stale_running_jobs,
    complete_job_run,
    create_job_run,
    get_job_run_count,
    get_job_run_history,
    get_last_job_run,
)
from argus.daemon.signals import SignalHandler
from argus.daemon.types import DaemonStatus, JobRunRecord, JobStatus
from argus.db.connection import get_connection

logger = logging.getLogger(__name__)

# Job IDs
JOB_INGEST = "ingest"
JOB_US_CLOSE = "us_close"
JOB_WEEKEND_WRAP = "weekend_wrap"
JOB_MONDAY_PREVIEW = "monday_preview"
JOB_RETENTION = "retention"
JOB_HEALTH_PING = "health_ping"

JOB_SEPARATOR = ":"

ALL_JOBS = [JOB_INGEST, JOB_US_CLOSE, JOB_WEEKEND_WRAP, JOB_MONDAY_PREVIEW, JOB_RETENTION]

# Jobs that should run immediately if missed (catch-up on restart)
CATCHUP_JOBS = {JOB_INGEST, JOB_RETENTION}


class ArgusDaemon:
    """Long-running daemon with internal scheduler.

    Handles:
    - Scheduled job execution (ingest, us_close, weekend_wrap, monday_preview, retention)
    - Timezone-aware scheduling (SGT for daily/weekend, NY for monday_preview)
    - Health endpoint for monitoring
    - Graceful shutdown handling
    - Job run history persistence

    Usage:
        daemon = ArgusDaemon(config)
        await daemon.start()
    """

    def __init__(self, config: ArgusConfig) -> None:
        """Initialize the daemon.

        Args:
            config: Argus configuration.
        """
        self.config = config
        self.daemon_config = config.daemon
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._health_server: Optional[HealthServer] = None
        self._signal_handler: Optional[SignalHandler] = None
        self._started_at: Optional[datetime] = None
        self._running_jobs: dict[str, int] = {}  # job_id -> record_id
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._telegram_task: Optional[asyncio.Task[None]] = None

    async def start(self) -> None:
        """Start the daemon and run until shutdown signal."""
        self._started_at = datetime.now(timezone.utc)
        self._loop = asyncio.get_event_loop()

        logger.info(f"Starting Argus daemon v{__version__}")

        # Setup signal handler
        self._signal_handler = SignalHandler()
        self._signal_handler.register(self._loop, self._on_shutdown_signal)

        # Cleanup any stale running jobs from previous session
        try:
            conn = get_connection()
            cleanup_stale_running_jobs(conn)
            conn.close()
        except Exception as e:
            logger.warning(f"Could not cleanup stale jobs: {e}")

        # Check for missed jobs that need catch-up
        await self._check_missed_jobs()

        # Setup scheduler
        self._scheduler = AsyncIOScheduler(timezone="UTC")
        self._setup_jobs()
        self._scheduler.start()

        # Start health server
        if self.daemon_config.health_port > 0:
            self._health_server = HealthServer(
                daemon=self,
                port=self.daemon_config.health_port,
                bind=self.daemon_config.health_bind,
            )
            await self._health_server.start()

        # Start Telegram control plane (best-effort; disabled if env missing)
        try:
            from argus.telegram_control.poller import run_telegram_control_plane

            self._telegram_task = asyncio.create_task(run_telegram_control_plane(self.config))
        except Exception as e:
            logger.warning(f"Telegram control plane not started: {e}")

        # Log one immediate heartbeat (then periodic below if enabled)
        self._log_health_ping()

        logger.info("Daemon started, waiting for shutdown signal...")

        # Wait for shutdown signal
        await self._signal_handler.wait_for_shutdown()

        # Graceful shutdown
        await self._shutdown()

    def _on_shutdown_signal(self) -> None:
        """Callback when shutdown signal is received."""
        logger.info("Shutdown signal received")

    async def _shutdown(self) -> None:
        """Perform graceful shutdown."""
        logger.info("Shutting down daemon...")

        # Stop accepting new jobs
        if self._scheduler:
            self._scheduler.shutdown(wait=True)
            logger.info("Scheduler stopped")

        # Stop Telegram control plane
        if self._telegram_task is not None:
            self._telegram_task.cancel()
            try:
                await self._telegram_task
            except asyncio.CancelledError:
                pass

        # Stop health server
        if self._health_server:
            await self._health_server.stop()

        # Wait for running jobs to complete (with timeout)
        if self._running_jobs:
            logger.info(f"Waiting for {len(self._running_jobs)} running job(s) to complete...")
            # Give running jobs up to 60 seconds to complete
            for _ in range(60):
                if not self._running_jobs:
                    break
                await asyncio.sleep(1)

            if self._running_jobs:
                logger.warning(f"Timeout waiting for jobs: {list(self._running_jobs.keys())}")

        logger.info("Daemon shutdown complete")

    def _setup_jobs(self) -> None:
        """Setup all scheduled jobs."""
        assert self._scheduler is not None

        for stream_name in self._iter_enabled_streams():
            stream_cfg = self.config.get_stream(stream_name)
            schedule = stream_cfg.schedule
            rss_config = stream_cfg.rss

            # Ingest job - runs every N minutes
            if self.daemon_config.is_job_enabled(JOB_INGEST):
                jid = self._job_key(JOB_INGEST, stream_name)
                self._scheduler.add_job(
                    self._run_ingest_for_stream,
                    IntervalTrigger(minutes=rss_config.poll_interval_minutes),
                    args=[stream_name],
                    id=jid,
                    name=f"RSS Ingestion ({stream_name})",
                    replace_existing=True,
                )
                logger.info(f"Scheduled {jid}: every {rss_config.poll_interval_minutes} minutes")

            # US Close job - Tue-Fri at configured time (SGT)
            if self.daemon_config.is_job_enabled(JOB_US_CLOSE):
                hour, minute = self._parse_time(schedule.daily_us_close_sgt)
                jid = self._job_key(JOB_US_CLOSE, stream_name)
                self._scheduler.add_job(
                    self._run_us_close_for_stream,
                    CronTrigger(
                        hour=hour,
                        minute=minute,
                        day_of_week="tue-fri",
                        timezone="Asia/Singapore",
                    ),
                    args=[stream_name],
                    id=jid,
                    name=f"US Close Update ({stream_name})",
                    replace_existing=True,
                )
                logger.info(f"Scheduled {jid}: Tue-Fri {schedule.daily_us_close_sgt} SGT")

            # Weekend Wrap job - Saturday at configured time (SGT)
            if self.daemon_config.is_job_enabled(JOB_WEEKEND_WRAP):
                hour, minute = self._parse_time(schedule.weekend_wrap_sgt)
                jid = self._job_key(JOB_WEEKEND_WRAP, stream_name)
                self._scheduler.add_job(
                    self._run_weekend_wrap_for_stream,
                    CronTrigger(
                        hour=hour,
                        minute=minute,
                        day_of_week="sat",
                        timezone="Asia/Singapore",
                    ),
                    args=[stream_name],
                    id=jid,
                    name=f"Weekend Wrap ({stream_name})",
                    replace_existing=True,
                )
                logger.info(f"Scheduled {jid}: Sat {schedule.weekend_wrap_sgt} SGT")

            # Monday Preview job - Sunday at configured time (NY)
            if self.daemon_config.is_job_enabled(JOB_MONDAY_PREVIEW):
                parts = schedule.monday_preview_ny.split()
                time_str = parts[-1] if len(parts) > 1 else parts[0]
                hour, minute = self._parse_time(time_str)
                jid = self._job_key(JOB_MONDAY_PREVIEW, stream_name)
                self._scheduler.add_job(
                    self._run_monday_preview_for_stream,
                    CronTrigger(
                        hour=hour,
                        minute=minute,
                        day_of_week="sun",
                        timezone="America/New_York",
                    ),
                    args=[stream_name],
                    id=jid,
                    name=f"Monday Preview ({stream_name})",
                    replace_existing=True,
                )
                logger.info(f"Scheduled {jid}: Sun {time_str} NY")

            # Retention job - daily at configured hour (UTC)
            if self.daemon_config.is_job_enabled(JOB_RETENTION):
                retention_hour = self.daemon_config.retention_hour
                jid = self._job_key(JOB_RETENTION, stream_name)
                self._scheduler.add_job(
                    self._run_retention_for_stream,
                    CronTrigger(hour=retention_hour, minute=0, timezone="UTC"),
                    args=[stream_name],
                    id=jid,
                    name=f"Retention Cleanup ({stream_name})",
                    replace_existing=True,
                )
                logger.info(f"Scheduled {jid}: daily at {retention_hour:02d}:00 UTC")

        # Journald heartbeat - every N minutes (0 disables)
        health_ping_minutes = getattr(self.daemon_config, "health_ping_minutes", 10)
        if health_ping_minutes > 0:
            self._scheduler.add_job(
                self._log_health_ping,
                IntervalTrigger(minutes=health_ping_minutes),
                id=JOB_HEALTH_PING,
                name="Health Ping",
                replace_existing=True,
            )
            logger.info(f"Scheduled {JOB_HEALTH_PING}: every {health_ping_minutes} minutes")

    def _parse_time(self, time_str: str) -> tuple[int, int]:
        """Parse a time string like '06:00' into (hour, minute)."""
        parts = time_str.split(":")
        return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0

    def _kv(self, **fields: object) -> str:
        """Format key=value pairs for journald-friendly logs."""
        # Keep formatting predictable and single-line.
        formatted: list[str] = []
        for key, value in fields.items():
            if value is None:
                continue
            if isinstance(value, bool):
                formatted.append(f"{key}={1 if value else 0}")
            else:
                formatted.append(f"{key}={value}")
        return " ".join(formatted)

    def _log_health_ping(self) -> None:
        """Log daemon liveness/health line for journald.

        Healthy case: one short INFO line.
        Degraded/unhealthy: one WARN/ERROR line + per-job detail lines for degraded jobs only.
        """
        try:
            status = self.get_status()

            jobs_total = len(status.jobs)
            jobs_enabled = sum(1 for j in status.jobs.values() if j.enabled)
            jobs_running = sum(1 for j in status.jobs.values() if j.is_running)

            # Degraded jobs are enabled jobs with last_status == 'failed'.
            degraded_jobs = [
                j.job_id
                for j in status.jobs.values()
                if j.enabled and j.last_status == "failed" and j.last_run is not None
            ]

            is_degraded = status.status in {"degraded", "unhealthy"} or len(degraded_jobs) > 0

            heartbeat_line = self._kv(
                event="health_ping",
                status=status.status,
                uptime_s=status.uptime_seconds,
                jobs_total=jobs_total,
                jobs_enabled=jobs_enabled,
                jobs_running=jobs_running,
                degraded=is_degraded,
                degraded_jobs=",".join(degraded_jobs) if degraded_jobs else None,
            )

            if is_degraded:
                # Use WARNING unless explicitly unhealthy.
                if status.status == "unhealthy":
                    logger.error(heartbeat_line)
                else:
                    logger.warning(heartbeat_line)

                for job_id in degraded_jobs:
                    job = status.jobs.get(job_id)
                    if job is None:
                        continue
                    logger.warning(
                        self._kv(
                            event="job_health",
                            job_id=job.job_id,
                            enabled=job.enabled,
                            is_running=job.is_running,
                            last_status=job.last_status,
                            last_run=job.last_run.isoformat() if job.last_run else None,
                            next_run=job.next_run.isoformat() if job.next_run else None,
                            run_count=job.run_count,
                        )
                    )
            else:
                logger.info(heartbeat_line)
        except Exception:
            # Heartbeat should never crash the daemon.
            logger.exception("event=health_ping status=error")

    def _job_key(self, job_id: str, stream_name: str) -> str:
        return f"{job_id}{JOB_SEPARATOR}{stream_name}"

    def _split_job_key(self, job_key: str) -> tuple[str, Optional[str]]:
        if JOB_SEPARATOR not in job_key:
            return job_key, None
        job_id, stream_name = job_key.split(JOB_SEPARATOR, 1)
        return job_id, stream_name or None

    def _iter_enabled_streams(self) -> list[str]:
        names = self.config.list_streams(enabled_only=True)
        return names or [self.config.stream.name]

    async def _check_missed_jobs(self) -> None:
        """Check for jobs that need catch-up after restart."""
        try:
            conn = get_connection()
            now = datetime.now(timezone.utc)

            for stream_name in self._iter_enabled_streams():
                stream_cfg = self.config.get_stream(stream_name)

                for job_id in CATCHUP_JOBS:
                    if not self.daemon_config.is_job_enabled(job_id):
                        continue

                    policy = self.daemon_config.get_missed_policy(job_id)
                    if policy != "run_immediately":
                        continue

                    job_key = self._job_key(job_id, stream_name)
                    last_run = get_last_job_run(conn, job_key)
                    if last_run is None:
                        # Never run before, trigger immediately
                        logger.info(f"Job {job_key} has never run, triggering catch-up")
                        await self._trigger_job(job_key, trigger_type="catchup")
                        continue

                    # Check if overdue based on expected interval
                    if job_id == JOB_INGEST:
                        interval_minutes = stream_cfg.rss.poll_interval_minutes
                        expected_interval = interval_minutes * 60  # seconds
                        elapsed = (now - last_run.started_at).total_seconds()
                        if elapsed > expected_interval * 2:  # 2x overdue
                            logger.info(
                                f"Job {job_key} is overdue (last run: {last_run.started_at}), "
                                "triggering catch-up"
                            )
                            await self._trigger_job(job_key, trigger_type="catchup")

            conn.close()
        except Exception as e:
            logger.warning(f"Error checking missed jobs: {e}")

    async def _trigger_job(
        self, job_id_or_key: str, trigger_type: str = "manual"
    ) -> Optional[JobRunRecord]:
        """Trigger a job immediately.

        Args:
            job_id_or_key: Job to trigger (base id like "ingest" or composite key like "ingest:alpha").
            trigger_type: Type of trigger ('manual', 'catchup', 'scheduled').

        Returns:
            JobRunRecord if job was executed, None if job is disabled or already running.
        """
        base_job_id, stream_name = self._split_job_key(job_id_or_key)

        if not self.daemon_config.is_job_enabled(base_job_id):
            logger.warning(f"Job {base_job_id} is disabled, skipping trigger")
            return None

        if stream_name is None:
            # Back-compat: single-stream trigger.
            job_key = base_job_id
        else:
            job_key = self._job_key(base_job_id, stream_name)

        if job_key in self._running_jobs:
            logger.warning(f"Job {job_key} is already running, skipping trigger")
            return None

        # Map base job id to handler
        handlers = {
            JOB_INGEST: self._run_ingest,
            JOB_US_CLOSE: self._run_us_close,
            JOB_WEEKEND_WRAP: self._run_weekend_wrap,
            JOB_MONDAY_PREVIEW: self._run_monday_preview,
            JOB_RETENTION: self._run_retention,
        }

        handler = handlers.get(base_job_id)
        if handler is None:
            logger.error(f"Unknown job: {base_job_id}")
            return None

        # Run the job
        return await handler(trigger_type=trigger_type, stream_name=stream_name)

    async def _run_job(
        self,
        job_id: str,
        job_func: Any,
        trigger_type: str = "scheduled",
        stream_name: Optional[str] = None,
    ) -> Optional[JobRunRecord]:
        """Run a job with tracking.

        Args:
            job_id: Job identifier.
            job_func: Callable to execute.
            trigger_type: Type of trigger.

        Returns:
            JobRunRecord with execution result.
        """
        conn = None
        record = None
        run_id = None

        try:
            conn = get_connection()

            # Create job run record
            record = create_job_run(conn, job_id, trigger_type)
            self._running_jobs[job_id] = record.id or 0

            logger.info(f"Starting job: {job_id} (trigger: {trigger_type})")

            # Execute the job
            cfg = self.config
            if stream_name is not None:
                cfg = replace(cfg, stream=cfg.get_stream(stream_name))

            result = await asyncio.get_event_loop().run_in_executor(None, job_func, cfg)

            # Extract run_id if available
            if hasattr(result, "run_id"):
                run_id = result.run_id

            # Mark as success
            complete_job_run(conn, record.id or 0, success=True, run_id=run_id)
            logger.info(f"Job completed: {job_id}")

            return record

        except Exception as e:
            logger.exception(f"Job failed: {job_id}")
            if conn and record and record.id:
                complete_job_run(conn, record.id, success=False, error_message=str(e))
            return record

        finally:
            if job_id in self._running_jobs:
                del self._running_jobs[job_id]
            if conn:
                conn.close()

    async def _run_ingest_for_stream(self, stream_name: str) -> Optional[JobRunRecord]:
        """Run RSS ingestion job for a specific stream."""
        from argus.ingestion import run_ingestion

        job_id = self._job_key(JOB_INGEST, stream_name)
        return await self._run_job(
            job_id, run_ingestion, trigger_type="scheduled", stream_name=stream_name
        )

    async def _run_ingest(
        self, trigger_type: str = "scheduled", stream_name: Optional[str] = None
    ) -> Optional[JobRunRecord]:
        """Run RSS ingestion job."""
        from argus.ingestion import run_ingestion

        if stream_name is None:
            return await self._run_job(JOB_INGEST, run_ingestion, trigger_type)

        job_id = self._job_key(JOB_INGEST, stream_name)
        return await self._run_job(job_id, run_ingestion, trigger_type, stream_name=stream_name)

    async def _run_us_close_for_stream(self, stream_name: str) -> Optional[JobRunRecord]:
        """Run US Close update job for a specific stream."""

        def run_us_close_sync(config: ArgusConfig) -> Any:
            from argus.orchestrator import OrchestratorOptions, RunOrchestrator, RunMode

            options = OrchestratorOptions(
                conditional=config.stream.monday_preview.conditional,
                force_publish=config.stream.monday_preview.force_publish,
                force_skip=config.stream.monday_preview.force_skip,
                risk_threshold=config.stream.monday_preview.risk_threshold,
            )
            orchestrator = RunOrchestrator(config, RunMode.US_CLOSE, options)
            return orchestrator.run()

        job_id = self._job_key(JOB_US_CLOSE, stream_name)
        return await self._run_job(
            job_id, run_us_close_sync, trigger_type="scheduled", stream_name=stream_name
        )

    async def _run_us_close(
        self, trigger_type: str = "scheduled", stream_name: Optional[str] = None
    ) -> Optional[JobRunRecord]:
        """Run US Close update job."""

        def run_us_close_sync(config: ArgusConfig) -> Any:
            from argus.orchestrator import OrchestratorOptions, RunOrchestrator, RunMode

            options = OrchestratorOptions(
                conditional=config.stream.monday_preview.conditional,
                force_publish=config.stream.monday_preview.force_publish,
                force_skip=config.stream.monday_preview.force_skip,
                risk_threshold=config.stream.monday_preview.risk_threshold,
            )
            orchestrator = RunOrchestrator(config, RunMode.US_CLOSE, options)
            return orchestrator.run()

        if stream_name is None:
            return await self._run_job(JOB_US_CLOSE, run_us_close_sync, trigger_type)

        job_id = self._job_key(JOB_US_CLOSE, stream_name)
        return await self._run_job(job_id, run_us_close_sync, trigger_type, stream_name=stream_name)

    async def _run_weekend_wrap_for_stream(self, stream_name: str) -> Optional[JobRunRecord]:
        """Run Weekend Wrap job for a specific stream."""

        def run_weekend_wrap_sync(config: ArgusConfig) -> Any:
            from argus.orchestrator import OrchestratorOptions, RunOrchestrator, RunMode

            options = OrchestratorOptions()
            orchestrator = RunOrchestrator(config, RunMode.WEEKEND_WRAP, options)
            return orchestrator.run()

        job_id = self._job_key(JOB_WEEKEND_WRAP, stream_name)
        return await self._run_job(
            job_id, run_weekend_wrap_sync, trigger_type="scheduled", stream_name=stream_name
        )

    async def _run_weekend_wrap(
        self, trigger_type: str = "scheduled", stream_name: Optional[str] = None
    ) -> Optional[JobRunRecord]:
        """Run Weekend Wrap job."""

        def run_weekend_wrap_sync(config: ArgusConfig) -> Any:
            from argus.orchestrator import OrchestratorOptions, RunOrchestrator, RunMode

            options = OrchestratorOptions()
            orchestrator = RunOrchestrator(config, RunMode.WEEKEND_WRAP, options)
            return orchestrator.run()

        if stream_name is None:
            return await self._run_job(JOB_WEEKEND_WRAP, run_weekend_wrap_sync, trigger_type)

        job_id = self._job_key(JOB_WEEKEND_WRAP, stream_name)
        return await self._run_job(
            job_id, run_weekend_wrap_sync, trigger_type, stream_name=stream_name
        )

    async def _run_monday_preview_for_stream(self, stream_name: str) -> Optional[JobRunRecord]:
        """Run Monday Preview job for a specific stream."""

        def run_monday_preview_sync(config: ArgusConfig) -> Any:
            from argus.orchestrator import OrchestratorOptions, RunOrchestrator, RunMode

            options = OrchestratorOptions(
                conditional=config.stream.monday_preview.conditional,
                force_publish=config.stream.monday_preview.force_publish,
                force_skip=config.stream.monday_preview.force_skip,
                risk_threshold=config.stream.monday_preview.risk_threshold,
            )
            orchestrator = RunOrchestrator(config, RunMode.MONDAY_PREVIEW, options)
            return orchestrator.run()

        job_id = self._job_key(JOB_MONDAY_PREVIEW, stream_name)
        return await self._run_job(
            job_id, run_monday_preview_sync, trigger_type="scheduled", stream_name=stream_name
        )

    async def _run_monday_preview(
        self, trigger_type: str = "scheduled", stream_name: Optional[str] = None
    ) -> Optional[JobRunRecord]:
        """Run Monday Preview job."""

        def run_monday_preview_sync(config: ArgusConfig) -> Any:
            from argus.orchestrator import OrchestratorOptions, RunOrchestrator, RunMode

            options = OrchestratorOptions(
                conditional=config.stream.monday_preview.conditional,
                force_publish=config.stream.monday_preview.force_publish,
                force_skip=config.stream.monday_preview.force_skip,
                risk_threshold=config.stream.monday_preview.risk_threshold,
            )
            orchestrator = RunOrchestrator(config, RunMode.MONDAY_PREVIEW, options)
            return orchestrator.run()

        if stream_name is None:
            return await self._run_job(JOB_MONDAY_PREVIEW, run_monday_preview_sync, trigger_type)

        job_id = self._job_key(JOB_MONDAY_PREVIEW, stream_name)
        return await self._run_job(
            job_id, run_monday_preview_sync, trigger_type, stream_name=stream_name
        )

    async def _run_retention_for_stream(self, stream_name: str) -> Optional[JobRunRecord]:
        """Run retention cleanup job for a specific stream."""

        def run_retention_sync(config: ArgusConfig) -> Any:
            from argus.db.partitions import run_retention_cleanup

            conn = get_connection()
            try:
                run_retention_cleanup(conn, config.stream.retention.news_items_days)
            finally:
                conn.close()
            return None

        job_id = self._job_key(JOB_RETENTION, stream_name)
        return await self._run_job(
            job_id, run_retention_sync, trigger_type="scheduled", stream_name=stream_name
        )

    async def _run_retention(
        self, trigger_type: str = "scheduled", stream_name: Optional[str] = None
    ) -> Optional[JobRunRecord]:
        """Run retention cleanup job."""

        def run_retention_sync(config: ArgusConfig) -> Any:
            from argus.db.partitions import run_retention_cleanup

            conn = get_connection()
            try:
                run_retention_cleanup(conn, config.stream.retention.news_items_days)
            finally:
                conn.close()
            return None

        if stream_name is None:
            return await self._run_job(JOB_RETENTION, run_retention_sync, trigger_type)

        job_id = self._job_key(JOB_RETENTION, stream_name)
        return await self._run_job(
            job_id, run_retention_sync, trigger_type, stream_name=stream_name
        )

    def get_status(self) -> DaemonStatus:
        """Get current daemon status.

        Returns:
            DaemonStatus with job information.
        """
        now = datetime.now(timezone.utc)
        uptime = int((now - self._started_at).total_seconds()) if self._started_at else 0

        # Get job statuses
        jobs: dict[str, JobStatus] = {}

        try:
            conn = get_connection()

            # Multi-stream jobs
            for stream_name in self._iter_enabled_streams():
                for base_job_id in ALL_JOBS:
                    job_key = self._job_key(base_job_id, stream_name)

                    last_run = get_last_job_run(conn, job_key)
                    run_count = get_job_run_count(conn, job_key)

                    # Get next run time from scheduler
                    next_run = None
                    if self._scheduler:
                        job = self._scheduler.get_job(job_key)
                        if job and job.next_run_time:
                            next_run = job.next_run_time

                    jobs[job_key] = JobStatus(
                        job_id=job_key,
                        enabled=self.daemon_config.is_job_enabled(base_job_id),
                        last_run=last_run.started_at if last_run else None,
                        last_status=last_run.status if last_run else None,
                        next_run=next_run,
                        run_count=run_count,
                        is_running=job_key in self._running_jobs,
                    )

            # Global jobs
            if self._scheduler:
                job = self._scheduler.get_job(JOB_HEALTH_PING)
                next_run = job.next_run_time if job and job.next_run_time else None
            else:
                next_run = None

            jobs[JOB_HEALTH_PING] = JobStatus(
                job_id=JOB_HEALTH_PING,
                enabled=True,
                last_run=None,
                last_status=None,
                next_run=next_run,
                run_count=0,
                is_running=JOB_HEALTH_PING in self._running_jobs,
            )

            conn.close()
        except Exception as e:
            logger.warning(f"Error getting job status: {e}")

        # Determine overall status
        status = "healthy"
        if any(job.last_status == "failed" for job in jobs.values() if job.last_run):
            status = "degraded"

        return DaemonStatus(
            status=status,
            uptime_seconds=uptime,
            version=__version__,
            started_at=self._started_at or now,
            jobs=jobs,
        )

    def get_job_history(self, job_id: str, limit: int = 10) -> list[JobRunRecord]:
        """Get recent run history for a job.

        Args:
            job_id: Job identifier.
            limit: Maximum number of records.

        Returns:
            List of JobRunRecords.
        """
        try:
            conn = get_connection()
            history = get_job_run_history(conn, job_id, limit)
            conn.close()
            return history
        except Exception as e:
            logger.warning(f"Error getting job history: {e}")
            return []

    async def trigger_job(self, job_id: str) -> Optional[JobRunRecord]:
        """Manually trigger a job.

        Args:
            job_id: Job to trigger.

        Returns:
            JobRunRecord if job was executed.
        """
        return await self._trigger_job(job_id, trigger_type="manual")
