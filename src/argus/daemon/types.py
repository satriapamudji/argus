"""Type definitions for the daemon module."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class JobRunRecord:
    """Record of a job execution.

    Attributes:
        id: Database ID (None if not persisted yet).
        job_id: Job identifier (e.g., 'ingest', 'us_close').
        started_at: When the job started.
        completed_at: When the job completed (None if still running).
        status: Job status ('running', 'success', 'failed').
        error_message: Error message if failed.
        duration_ms: Duration in milliseconds.
        run_id: Associated run ID from runs table (if applicable).
        trigger_type: How the job was triggered ('scheduled', 'manual', 'catchup').
    """

    job_id: str
    started_at: datetime
    status: str
    id: Optional[int] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    duration_ms: Optional[int] = None
    run_id: Optional[int] = None
    trigger_type: str = "scheduled"


@dataclass
class JobStatus:
    """Current status of a scheduled job.

    Attributes:
        job_id: Job identifier.
        enabled: Whether the job is enabled.
        last_run: Timestamp of last run (None if never run).
        last_status: Status of last run ('success', 'failed', None).
        next_run: Timestamp of next scheduled run (None if not scheduled).
        run_count: Total number of runs.
        is_running: Whether the job is currently running.
    """

    job_id: str
    enabled: bool = True
    last_run: Optional[datetime] = None
    last_status: Optional[str] = None
    next_run: Optional[datetime] = None
    run_count: int = 0
    is_running: bool = False


@dataclass
class DaemonStatus:
    """Overall daemon status.

    Attributes:
        status: Overall status ('healthy', 'degraded', 'unhealthy').
        uptime_seconds: Seconds since daemon started.
        version: Argus version.
        jobs: Status of each job.
        started_at: When the daemon started.
    """

    status: str
    uptime_seconds: int
    version: str
    started_at: datetime
    jobs: dict[str, JobStatus] = field(default_factory=dict)
