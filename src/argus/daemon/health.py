"""HTTP health endpoint for daemon monitoring.

Provides a simple HTTP server with health check endpoints.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

from aiohttp import web

from argus import __version__
from argus.daemon.types import DaemonStatus, JobStatus


class DaemonProtocol(Protocol):
    """Protocol for ArgusDaemon to avoid circular imports."""

    daemon_config: Any

    def get_status(self) -> DaemonStatus: ...
    def get_job_history(self, job_id: str, limit: int = 10) -> list: ...
    async def trigger_job(self, job_id: str) -> Any: ...


logger = logging.getLogger(__name__)


class HealthServer:
    """HTTP server for health check endpoints.

    Provides:
    - GET /health - Overall daemon health and job status
    - GET /health/jobs/{job_id}/history - Recent run history for a job

    Usage:
        server = HealthServer(daemon, port=8080, bind="127.0.0.1")
        await server.start()
        # ... daemon runs ...
        await server.stop()
    """

    def __init__(
        self,
        daemon: DaemonProtocol,
        port: int = 8080,
        bind: str = "127.0.0.1",
    ) -> None:
        """Initialize the health server.

        Args:
            daemon: The ArgusDaemon instance to monitor.
            port: Port to listen on.
            bind: Address to bind to (default localhost only).
        """
        self.daemon = daemon
        self.port = port
        self.bind = bind
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None

    async def start(self) -> None:
        """Start the health server."""
        self._app = web.Application()
        self._app.router.add_get("/health", self._handle_health)
        self._app.router.add_get("/health/jobs/{job_id}/history", self._handle_job_history)
        self._app.router.add_post("/trigger/{job_id}", self._handle_trigger)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        self._site = web.TCPSite(self._runner, self.bind, self.port)
        await self._site.start()

        logger.info(f"Health server started on http://{self.bind}:{self.port}/health")

    async def stop(self) -> None:
        """Stop the health server."""
        if self._runner:
            await self._runner.cleanup()
            logger.info("Health server stopped")

    async def _handle_health(self, request: web.Request) -> web.Response:  # noqa: ARG002
        """Handle GET /health request.

        Returns overall daemon status and job information.
        """
        try:
            status = self.daemon.get_status()
            response_data = self._serialize_status(status)

            return web.Response(
                text=json.dumps(response_data, indent=2, default=str),
                content_type="application/json",
            )
        except Exception as e:
            logger.exception("Error handling health request")
            return web.Response(
                text=json.dumps({"error": str(e)}),
                status=500,
                content_type="application/json",
            )

    async def _handle_job_history(self, request: web.Request) -> web.Response:
        """Handle GET /health/jobs/{job_id}/history request.

        Returns recent run history for a specific job.
        """
        job_id = request.match_info.get("job_id", "")
        limit = int(request.query.get("limit", "10"))

        try:
            history = self.daemon.get_job_history(job_id, limit=limit)

            response_data = {
                "job_id": job_id,
                "history": [
                    {
                        "id": run.id,
                        "started_at": run.started_at.isoformat() if run.started_at else None,
                        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                        "status": run.status,
                        "duration_ms": run.duration_ms,
                        "error_message": run.error_message,
                        "trigger_type": run.trigger_type,
                    }
                    for run in history
                ],
            }

            return web.Response(
                text=json.dumps(response_data, indent=2),
                content_type="application/json",
            )
        except Exception as e:
            logger.exception(f"Error handling job history request for {job_id}")
            return web.Response(
                text=json.dumps({"error": str(e)}),
                status=500,
                content_type="application/json",
            )

    def _serialize_status(self, status: DaemonStatus) -> dict[str, Any]:
        """Serialize DaemonStatus to JSON-compatible dict."""
        return {
            "status": status.status,
            "uptime_seconds": status.uptime_seconds,
            "version": status.version,
            "started_at": status.started_at.isoformat(),
            "jobs": {
                job_id: self._serialize_job_status(job_status)
                for job_id, job_status in status.jobs.items()
            },
        }

    def _serialize_job_status(self, job_status: JobStatus) -> dict[str, Any]:
        """Serialize JobStatus to JSON-compatible dict."""
        return {
            "enabled": job_status.enabled,
            "last_run": job_status.last_run.isoformat() if job_status.last_run else None,
            "last_status": job_status.last_status,
            "next_run": job_status.next_run.isoformat() if job_status.next_run else None,
            "run_count": job_status.run_count,
            "is_running": job_status.is_running,
        }

    async def _handle_trigger(self, request: web.Request) -> web.Response:
        """Handle POST /trigger/{job_id} request.

        Manually triggers a scheduled job.

        Supports both base job IDs (single-stream) and composite "job:stream" keys.
        """
        job_key = request.match_info.get("job_id", "")

        from argus.daemon.scheduler import ALL_JOBS, JOB_SEPARATOR

        base_job_id = job_key.split(JOB_SEPARATOR, 1)[0]
        if base_job_id not in ALL_JOBS:
            return web.Response(
                text=json.dumps({"status": "error", "message": f"Unknown job: {job_key}"}),
                status=400,
                content_type="application/json",
            )

        try:
            # Check if job is enabled
            if not self.daemon.daemon_config.is_job_enabled(base_job_id):
                return web.Response(
                    text=json.dumps({"status": "disabled", "job_id": job_key}),
                    content_type="application/json",
                )

            # Trigger the job
            result = await self.daemon.trigger_job(job_key)

            if result is None:
                # Job was already running or disabled
                return web.Response(
                    text=json.dumps({"status": "already_running", "job_id": job_key}),
                    content_type="application/json",
                )

            return web.Response(
                text=json.dumps(
                    {
                        "status": "triggered",
                        "job_id": job_key,
                        "run_id": result.id,
                    }
                ),
                content_type="application/json",
            )
        except Exception as e:
            logger.exception(f"Error triggering job {job_key}")
            return web.Response(
                text=json.dumps({"status": "error", "message": str(e)}),
                status=500,
                content_type="application/json",
            )
