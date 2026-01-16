"""Tests for the daemon scheduler module."""

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from argus.config import ArgusConfig, DaemonConfig
from argus.daemon.scheduler import ArgusDaemon
from argus.daemon.types import DaemonStatus, JobRunRecord, JobStatus

# Pyright: pytest marks are dynamically created.
# This alias avoids reportUndefinedVariable for `@pytest.mark.db`.
db = pytest.mark.db


class TestDaemonConfig:
    """Tests for DaemonConfig."""

    def test_default_values(self):
        """Test default DaemonConfig values."""
        config = DaemonConfig()
        assert config.health_port == 8080
        assert config.health_bind == "127.0.0.1"
        assert config.retention_hour == 3
        assert config.health_ping_minutes == 10

    def test_is_job_enabled_default(self):
        """Test all jobs enabled by default."""
        config = DaemonConfig()
        assert config.is_job_enabled("ingest") is True
        assert config.is_job_enabled("us_close") is True
        assert config.is_job_enabled("weekend_wrap") is True
        assert config.is_job_enabled("monday_preview") is True
        assert config.is_job_enabled("retention") is True

    def test_is_job_enabled_disabled(self):
        """Test job can be disabled via config."""
        config = DaemonConfig(jobs_enabled={"ingest": False, "us_close": True})
        assert config.is_job_enabled("ingest") is False
        assert config.is_job_enabled("us_close") is True
        # Unknown job defaults to True
        assert config.is_job_enabled("weekend_wrap") is True

    def test_get_missed_policy_default(self):
        """Test default missed policies."""
        config = DaemonConfig()
        # Defaults: ingest and retention run immediately, others skip
        assert config.get_missed_policy("ingest") == "run_immediately"
        assert config.get_missed_policy("retention") == "run_immediately"
        assert config.get_missed_policy("us_close") == "skip"
        assert config.get_missed_policy("weekend_wrap") == "skip"
        assert config.get_missed_policy("monday_preview") == "skip"

    def test_get_missed_policy_custom(self):
        """Test custom missed policies."""
        config = DaemonConfig(missed_policy={"ingest": "skip", "us_close": "run_immediately"})
        assert config.get_missed_policy("ingest") == "skip"
        assert config.get_missed_policy("us_close") == "run_immediately"
        # Unspecified job falls back to "skip" (default fallback, not default dict)
        assert config.get_missed_policy("retention") == "skip"
        assert config.get_missed_policy("unknown_job") == "skip"


class TestDaemonConfigFromYaml:
    """Test daemon config loading from YAML."""

    def test_load_daemon_config_from_yaml(self):
        """Test loading daemon config from YAML file."""
        config_content = {
            "daemon": {
                "health_port": 9090,
                "health_bind": "0.0.0.0",
                "retention_hour": 5,
                "health_ping_minutes": 7,
                "jobs_enabled": {
                    "ingest": True,
                    "us_close": False,
                },
                "missed_policy": {
                    "ingest": "skip",
                },
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_content, f)
            config_path = Path(f.name)

        try:
            config = ArgusConfig.load(config_path=config_path)
            assert config.daemon.health_port == 9090
            assert config.daemon.health_bind == "0.0.0.0"
            assert config.daemon.retention_hour == 5
            assert config.daemon.health_ping_minutes == 7
            assert config.daemon.is_job_enabled("ingest") is True
            assert config.daemon.is_job_enabled("us_close") is False
            assert config.daemon.get_missed_policy("ingest") == "skip"
        finally:
            config_path.unlink()


class TestJobRunRecord:
    """Tests for JobRunRecord dataclass."""

    def test_create_job_run_record(self):
        """Test creating a JobRunRecord."""
        now = datetime.now(timezone.utc)
        record = JobRunRecord(
            job_id="ingest",
            started_at=now,
            status="running",
            trigger_type="scheduled",
        )
        assert record.job_id == "ingest"
        assert record.started_at == now
        assert record.status == "running"
        assert record.trigger_type == "scheduled"
        assert record.id is None
        assert record.completed_at is None
        assert record.error_message is None
        assert record.duration_ms is None
        assert record.run_id is None

    def test_job_run_record_with_all_fields(self):
        """Test JobRunRecord with all fields populated."""
        now = datetime.now(timezone.utc)
        record = JobRunRecord(
            id=42,
            job_id="us_close",
            started_at=now,
            completed_at=now,
            status="success",
            error_message=None,
            duration_ms=1500,
            run_id=100,
            trigger_type="manual",
        )
        assert record.id == 42
        assert record.duration_ms == 1500
        assert record.run_id == 100
        assert record.trigger_type == "manual"


class TestJobStatus:
    """Tests for JobStatus dataclass."""

    def test_job_status_defaults(self):
        """Test JobStatus default values."""
        status = JobStatus(job_id="ingest")
        assert status.job_id == "ingest"
        assert status.enabled is True
        assert status.last_run is None
        assert status.last_status is None
        assert status.next_run is None
        assert status.run_count == 0
        assert status.is_running is False


class TestDaemonStatus:
    """Tests for DaemonStatus dataclass."""

    def test_daemon_status_healthy(self):
        """Test creating a healthy DaemonStatus."""
        now = datetime.now(timezone.utc)
        jobs = {
            "ingest": JobStatus(
                job_id="ingest",
                enabled=True,
                last_status="success",
                run_count=42,
            ),
        }
        status = DaemonStatus(
            status="healthy",
            uptime_seconds=3600,
            version="0.1.0",
            started_at=now,
            jobs=jobs,
        )
        assert status.status == "healthy"
        assert status.uptime_seconds == 3600
        assert status.version == "0.1.0"
        assert "ingest" in status.jobs
        assert status.jobs["ingest"].run_count == 42


class TestDaemonPersistence:
    """Tests for daemon persistence layer.

    Note: These tests require a database connection.
    Marked with pytest.mark.db to allow selective running.
    """

    @db
    def test_create_and_complete_job_run(self):
        """Test creating and completing a job run record."""
        # This test requires actual database setup
        # Skip if no database available
        pytest.skip("Requires database connection - run with --run-db flag")


class TestDaemonSchedulingMultiStream:
    def test_setup_jobs_creates_per_stream_ids(self, tmp_path: Path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            """
streams:
  alpha:
    enabled: true
    rss:
      poll_interval_minutes: 5
  beta:
    enabled: true
    rss:
      poll_interval_minutes: 7
daemon:
  health_port: 0
""".lstrip(),
            encoding="utf-8",
        )
        config = ArgusConfig.load(config_path=config_path)
        daemon = ArgusDaemon(config)

        scheduler = MagicMock()
        daemon._scheduler = scheduler

        daemon._setup_jobs()

        job_ids = [kwargs.get("id") for _, kwargs in scheduler.add_job.call_args_list]
        assert "ingest:alpha" in job_ids
        assert "ingest:beta" in job_ids
        assert "us_close:alpha" in job_ids
        assert "us_close:beta" in job_ids
        assert "weekend_wrap:alpha" in job_ids
        assert "weekend_wrap:beta" in job_ids
        assert "monday_preview:alpha" in job_ids
        assert "monday_preview:beta" in job_ids
        assert "retention:alpha" in job_ids
        assert "retention:beta" in job_ids

        # Ensure crypto_daily uses kwargs for stream_name (avoid passing stream_name as trigger_type)
        crypto_calls = [
            kwargs
            for _, kwargs in scheduler.add_job.call_args_list
            if kwargs.get("id") in {"crypto_daily:alpha", "crypto_daily:beta"}
        ]
        assert len(crypto_calls) == 2
        for call_kwargs in crypto_calls:
            assert call_kwargs.get("kwargs", {}).get("stream_name") in {"alpha", "beta"}


class TestHealthServerSerialization:
    """Tests for health server response serialization."""

    def test_serialize_job_status(self):
        """Test JobStatus serialization to dict."""
        now = datetime.now(timezone.utc)
        status = JobStatus(
            job_id="ingest",
            enabled=True,
            last_run=now,
            last_status="success",
            next_run=now,
            run_count=42,
            is_running=False,
        )

        # Simulate serialization
        serialized = {
            "enabled": status.enabled,
            "last_run": status.last_run.isoformat() if status.last_run else None,
            "last_status": status.last_status,
            "next_run": status.next_run.isoformat() if status.next_run else None,
            "run_count": status.run_count,
            "is_running": status.is_running,
        }

        assert serialized["enabled"] is True
        assert serialized["last_status"] == "success"
        assert serialized["run_count"] == 42
        assert serialized["is_running"] is False
        assert serialized["last_run"] is not None

    def test_serialize_daemon_status(self):
        """Test DaemonStatus serialization to dict."""
        now = datetime.now(timezone.utc)
        status = DaemonStatus(
            status="healthy",
            uptime_seconds=7200,
            version="0.1.0",
            started_at=now,
            jobs={
                "ingest:alpha": JobStatus(job_id="ingest:alpha", run_count=100),
            },
        )

        # Simulate serialization
        serialized = {
            "status": status.status,
            "uptime_seconds": status.uptime_seconds,
            "version": status.version,
            "started_at": status.started_at.isoformat(),
            "jobs": {
                job_id: {
                    "enabled": job.enabled,
                    "run_count": job.run_count,
                }
                for job_id, job in status.jobs.items()
            },
        }

        assert serialized["status"] == "healthy"
        assert serialized["uptime_seconds"] == 7200
        assert serialized["version"] == "0.1.0"
        assert "ingest:alpha" in serialized["jobs"]
        assert serialized["jobs"]["ingest:alpha"]["run_count"] == 100


class TestSchedulerJobIds:
    """Tests for scheduler job ID constants."""

    def test_all_jobs_constant(self):
        """Test ALL_JOBS contains expected jobs."""
        from argus.daemon.scheduler import ALL_JOBS

        assert "ingest" in ALL_JOBS
        assert "us_close" in ALL_JOBS
        assert "weekend_wrap" in ALL_JOBS
        assert "monday_preview" in ALL_JOBS
        assert "crypto_daily" in ALL_JOBS
        assert "retention" in ALL_JOBS
        assert len(ALL_JOBS) == 6

    def test_catchup_jobs_constant(self):
        """Test CATCHUP_JOBS contains expected jobs."""
        from argus.daemon.scheduler import CATCHUP_JOBS

        assert "ingest" in CATCHUP_JOBS
        assert "retention" in CATCHUP_JOBS
        # Message jobs should not be in catchup
        assert "us_close" not in CATCHUP_JOBS
        assert "weekend_wrap" not in CATCHUP_JOBS
        assert "monday_preview" not in CATCHUP_JOBS
