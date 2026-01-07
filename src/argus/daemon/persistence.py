"""Persistence layer for scheduler job run history.

Handles storing and retrieving job execution records from the database.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from psycopg2.extensions import connection as Connection

from argus.daemon.types import JobRunRecord

logger = logging.getLogger(__name__)


def create_job_run(
    conn: Connection,
    job_id: str,
    trigger_type: str = "scheduled",
) -> JobRunRecord:
    """Create a new job run record (status='running').

    Args:
        conn: Database connection.
        job_id: Job identifier (e.g., 'ingest', 'us_close').
        trigger_type: How the job was triggered ('scheduled', 'manual', 'catchup').

    Returns:
        Created JobRunRecord with database ID.
    """
    started_at = datetime.now(timezone.utc)

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO scheduler_job_runs (job_id, started_at, status, trigger_type)
            VALUES (%s, %s, 'running', %s)
            RETURNING id
            """,
            (job_id, started_at, trigger_type),
        )
        row = cur.fetchone()
        record_id = row[0] if row else None
        conn.commit()

    record = JobRunRecord(
        id=record_id,
        job_id=job_id,
        started_at=started_at,
        status="running",
        trigger_type=trigger_type,
    )

    logger.debug(f"Created job run record: {record.id} for job {job_id}")
    return record


def complete_job_run(
    conn: Connection,
    record_id: int,
    success: bool,
    error_message: Optional[str] = None,
    run_id: Optional[int] = None,
) -> None:
    """Mark a job run as completed.

    Args:
        conn: Database connection.
        record_id: ID of the job run record.
        success: Whether the job succeeded.
        error_message: Error message if failed.
        run_id: Associated run ID from runs table (if applicable).
    """
    completed_at = datetime.now(timezone.utc)
    status = "success" if success else "failed"

    with conn.cursor() as cur:
        # First get the started_at to calculate duration
        cur.execute(
            "SELECT started_at FROM scheduler_job_runs WHERE id = %s",
            (record_id,),
        )
        row = cur.fetchone()
        if row:
            started_at = row[0]
            duration_ms = int((completed_at - started_at).total_seconds() * 1000)
        else:
            duration_ms = None

        cur.execute(
            """
            UPDATE scheduler_job_runs
            SET completed_at = %s, status = %s, error_message = %s, 
                duration_ms = %s, run_id = %s
            WHERE id = %s
            """,
            (completed_at, status, error_message, duration_ms, run_id, record_id),
        )
        conn.commit()

    logger.debug(f"Completed job run record: {record_id} with status {status}")


def get_last_job_run(
    conn: Connection,
    job_id: str,
) -> Optional[JobRunRecord]:
    """Get the most recent run for a job.

    Args:
        conn: Database connection.
        job_id: Job identifier.

    Returns:
        Most recent JobRunRecord or None if never run.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, job_id, started_at, completed_at, status, 
                   error_message, duration_ms, run_id, trigger_type
            FROM scheduler_job_runs
            WHERE job_id = %s
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (job_id,),
        )
        row = cur.fetchone()

    if row is None:
        return None

    return JobRunRecord(
        id=row[0],
        job_id=row[1],
        started_at=row[2],
        completed_at=row[3],
        status=row[4],
        error_message=row[5],
        duration_ms=row[6],
        run_id=row[7],
        trigger_type=row[8],
    )


def get_job_run_count(
    conn: Connection,
    job_id: str,
) -> int:
    """Get total run count for a job.

    Args:
        conn: Database connection.
        job_id: Job identifier.

    Returns:
        Total number of runs for this job.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM scheduler_job_runs WHERE job_id = %s",
            (job_id,),
        )
        row = cur.fetchone()

    return row[0] if row else 0


def get_job_run_history(
    conn: Connection,
    job_id: str,
    limit: int = 10,
) -> list[JobRunRecord]:
    """Get recent run history for a job.

    Args:
        conn: Database connection.
        job_id: Job identifier.
        limit: Maximum number of records to return.

    Returns:
        List of JobRunRecords, most recent first.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, job_id, started_at, completed_at, status, 
                   error_message, duration_ms, run_id, trigger_type
            FROM scheduler_job_runs
            WHERE job_id = %s
            ORDER BY started_at DESC
            LIMIT %s
            """,
            (job_id, limit),
        )
        rows = cur.fetchall()

    return [
        JobRunRecord(
            id=row[0],
            job_id=row[1],
            started_at=row[2],
            completed_at=row[3],
            status=row[4],
            error_message=row[5],
            duration_ms=row[6],
            run_id=row[7],
            trigger_type=row[8],
        )
        for row in rows
    ]


def get_running_jobs(conn: Connection) -> list[JobRunRecord]:
    """Get all currently running jobs.

    Args:
        conn: Database connection.

    Returns:
        List of JobRunRecords with status='running'.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, job_id, started_at, completed_at, status, 
                   error_message, duration_ms, run_id, trigger_type
            FROM scheduler_job_runs
            WHERE status = 'running'
            ORDER BY started_at DESC
            """,
        )
        rows = cur.fetchall()

    return [
        JobRunRecord(
            id=row[0],
            job_id=row[1],
            started_at=row[2],
            completed_at=row[3],
            status=row[4],
            error_message=row[5],
            duration_ms=row[6],
            run_id=row[7],
            trigger_type=row[8],
        )
        for row in rows
    ]


def cleanup_stale_running_jobs(conn: Connection) -> int:
    """Mark stale 'running' jobs as 'failed'.

    Called on daemon startup to clean up jobs that were interrupted
    by a previous crash or shutdown.

    Args:
        conn: Database connection.

    Returns:
        Number of jobs marked as failed.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE scheduler_job_runs
            SET status = 'failed', 
                error_message = 'Daemon interrupted (stale running job)',
                completed_at = NOW()
            WHERE status = 'running'
            RETURNING id
            """,
        )
        rows = cur.fetchall()
        conn.commit()

    count = len(rows)
    if count > 0:
        logger.warning(f"Cleaned up {count} stale running job(s) from previous session")

    return count
