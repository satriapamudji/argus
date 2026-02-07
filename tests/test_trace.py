"""Tests for the trace module - DB-free pipeline execution."""

import json
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from argus.trace.types import ScoredItemTrace, StageTrace, TraceOutput, create_stage_trace


def get_pythonpath() -> str:
    """Get PYTHONPATH with src directory included."""
    return str(Path(__file__).parent.parent / "src")


class TestTraceTypes:
    """Tests for trace data types."""

    def test_stage_trace_creation(self):
        """Test creating a StageTrace via helper function."""
        started = datetime.now(timezone.utc)
        completed = datetime.now(timezone.utc)

        stage = create_stage_trace(
            name="test_stage",
            started_at=started,
            completed_at=completed,
            item_count=10,
            artifacts={"key": "value"},
            errors=["error1"],
        )

        assert stage.name == "test_stage"
        assert stage.item_count == 10
        assert stage.artifacts == {"key": "value"}
        assert stage.errors == ["error1"]
        assert stage.duration_ms >= 0

    def test_trace_output_to_dict(self):
        """Test TraceOutput serialization to dict."""
        trace = TraceOutput(
            run_id="test123",
            stream_name="us_markets",
            run_mode="us_close",
            trading_date="2025-01-26",
            scoring_version="v2",
            started_at=datetime.now(timezone.utc).isoformat(),
            completed_at=None,
        )

        # Add a stage
        stage = create_stage_trace(
            name="ingest",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            item_count=5,
        )
        trace.add_stage(stage)

        # Add a scored item
        trace.all_scored_items.append(
            ScoredItemTrace(
                news_item_id=1,
                title="Test Article",
                source_name="Test Source",
                source_url="https://example.com/article",
                published_at=datetime.now(timezone.utc).isoformat(),
                impact_score=75,
                quality_score=80,
                confidence_score=90,
                topic="markets",
                reasons=["High impact keywords"],
                flags=[],
                breakdown=None,
                selected_for_bundle=True,
            )
        )

        trace.finalize()
        result = trace.to_dict()

        assert result["run_id"] == "test123"
        assert result["stream_name"] == "us_markets"
        assert len(result["stages"]) == 1
        assert len(result["all_scored_items"]) == 1
        assert result["completed_at"] is not None

    def test_scored_item_trace_to_dict(self):
        """Test ScoredItemTrace serialization."""
        item = ScoredItemTrace(
            news_item_id=42,
            title="Test Title",
            source_name="Test Source",
            source_url="https://example.com",
            published_at="2025-01-26T12:00:00Z",
            impact_score=85,
            quality_score=90,
            confidence_score=85,
            topic="earnings",
            reasons=["Breaking news", "Major company"],
            flags=["BREAKING"],
            breakdown={"recency": 10, "source_tier": 20},
            selected_for_bundle=True,
        )

        result = item.to_dict()

        assert result["news_item_id"] == 42
        assert result["title"] == "Test Title"
        assert result["impact_score"] == 85
        assert result["topic"] == "earnings"
        assert result["selected_for_bundle"] is True
        assert len(result["reasons"]) == 2


class TestTraceCalendar:
    """Tests for trace calendar module."""

    def test_format_raw_event_display(self):
        """Test formatting of raw economic events."""
        from argus.adapters.economic_calendar.types import RawEconomicEvent
        from argus.trace.calendar import format_raw_event_display

        event = RawEconomicEvent(
            title="Non-Farm Payrolls",
            country="USD",
            impact="High",
            timestamp_utc=datetime(2025, 1, 10, 14, 30, tzinfo=timezone.utc),
        )

        result = format_raw_event_display(event)

        assert "Jan" in result
        assert "14:30" in result
        assert "Non-Farm Payrolls" in result

    def test_raw_event_to_bundle(self):
        """Test conversion of raw event to bundle format."""
        from argus.adapters.economic_calendar.types import RawEconomicEvent
        from argus.trace.calendar import raw_event_to_bundle

        event = RawEconomicEvent(
            title="FOMC Meeting",
            country="USD",
            impact="High",
            timestamp_utc=datetime(2025, 1, 29, 19, 0, tzinfo=timezone.utc),
        )

        bundle = raw_event_to_bundle(event)

        assert bundle.name == "FOMC Meeting"
        assert bundle.timestamp_utc == event.timestamp_utc
        assert bundle.event_type == "economic"
        assert "FOMC Meeting" in bundle.formatted_display


class TestTraceWeeklyStats:
    """Tests for trace weekly stats module."""

    def test_fetch_weekly_stats_structure(self):
        """Test that fetch_weekly_stats returns expected structure."""
        from argus.trace.weekly_stats import fetch_weekly_stats

        # This will attempt a network call but should handle gracefully
        # if yfinance is unavailable or market data fails
        with patch("argus.trace.weekly_stats._get_yfinance") as mock_get_yf:
            # Mock yfinance to avoid network call
            mock_yf = MagicMock()
            mock_ticker = MagicMock()
            mock_ticker.history.return_value = MagicMock(empty=True)
            mock_yf.Ticker.return_value = mock_ticker
            mock_get_yf.return_value = mock_yf

            result = fetch_weekly_stats("weekend_wrap", date.today())

            # Should return None if no data available
            # (or a valid WeeklyStatsBundle if data exists)
            assert result is None or hasattr(result, "sp500_ytd_pct")


class TestTraceCLI:
    """Tests for trace CLI command."""

    def test_trace_help(self):
        """Test that trace --help works."""
        env = {**os.environ}
        env["PYTHONPATH"] = get_pythonpath()
        result = subprocess.run(
            [sys.executable, "-m", "argus", "trace", "--help"],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0
        assert "DB-free pipeline trace" in result.stdout
        assert "--stream" in result.stdout
        assert "--output" in result.stdout
        assert "--skip-generate" in result.stdout

    def test_trace_requires_stream(self):
        """Test that trace command requires --stream."""
        env = {**os.environ}
        env["PYTHONPATH"] = get_pythonpath()
        result = subprocess.run(
            [sys.executable, "-m", "argus", "trace", "--output", "trace.json"],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode != 0
        assert "Missing option" in result.stderr or "--stream" in result.stderr

    def test_trace_requires_output(self):
        """Test that trace command requires --output."""
        env = {**os.environ}
        env["PYTHONPATH"] = get_pythonpath()
        result = subprocess.run(
            [sys.executable, "-m", "argus", "trace", "--stream", "us_markets"],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode != 0
        assert "Missing option" in result.stderr or "--output" in result.stderr


class TestNoDBAccess:
    """Tests to verify trace module does not access database."""

    def test_runner_imports_no_db_modules(self):
        """Verify runner.py doesn't import DB modules at module level."""
        import ast
        from pathlib import Path

        runner_path = Path(__file__).parent.parent / "src" / "argus" / "trace" / "runner.py"
        with open(runner_path) as f:
            tree = ast.parse(f.read())

        # Check all imports
        db_imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if "argus.db" in alias.name or alias.name.startswith("psycopg"):
                        db_imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module and ("argus.db" in node.module or node.module.startswith("psycopg")):
                    db_imports.append(node.module)

        assert db_imports == [], f"DB modules imported in runner.py: {db_imports}"

    def test_bundle_builder_imports_no_db_modules(self):
        """Verify bundle_builder.py doesn't import DB modules at module level."""
        import ast
        from pathlib import Path

        builder_path = (
            Path(__file__).parent.parent / "src" / "argus" / "trace" / "bundle_builder.py"
        )
        with open(builder_path) as f:
            tree = ast.parse(f.read())

        # Check all imports
        db_imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if "argus.db" in alias.name or alias.name.startswith("psycopg"):
                        db_imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module and ("argus.db" in node.module or node.module.startswith("psycopg")):
                    db_imports.append(node.module)

        assert db_imports == [], f"DB modules imported in bundle_builder.py: {db_imports}"

    def test_run_trace_with_mocked_db_raises_on_access(self, monkeypatch, tmp_path):
        """Test that run_trace fails if DB is accessed (via monkeypatch)."""

        # Monkeypatch get_connection to raise if called
        def fail_on_db_access(*args, **kwargs):
            raise RuntimeError("DATABASE ACCESS DETECTED - trace module should be DB-free!")

        # Patch at multiple levels to catch any DB access
        monkeypatch.setattr("argus.db.connection.get_connection", fail_on_db_access, raising=False)

        # Import after patching
        from argus.config import ArgusConfig
        from argus.trace.runner import run_trace

        # Create a minimal config
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            """
streams:
  test_stream:
    enabled: true
    scoring:
      enabled: true
      version: v2
    rss:
      allowlist_files: []
      poll_interval_minutes: 20
    generator:
      model: "test-model"
      temperature: 0.7
      max_tokens: 4000
"""
        )

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
        monkeypatch.setenv("OPENROUTER_API_KEY", "test")

        # Load config
        config = ArgusConfig.load(config_path)
        config.select_stream("test_stream")

        # Run trace with skip_generate to avoid LLM call
        # This should work without hitting the DB
        try:
            result = run_trace(
                config=config,
                run_mode="us_close",
                skip_generate=True,
            )
            # If we get here without RuntimeError, DB was not accessed
            assert result is not None
            assert result.run_id is not None
        except RuntimeError as e:
            if "DATABASE ACCESS DETECTED" in str(e):
                pytest.fail("Trace module accessed database when it should be DB-free!")
            raise
