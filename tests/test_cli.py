"""Tests for CLI commands."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


def get_pythonpath() -> str:
    """Get PYTHONPATH with src directory included."""
    return str(Path(__file__).parent.parent / "src")


class TestCLI:
    """Tests for CLI entrypoint."""

    def test_help_command(self):
        """Test that --help works."""
        env = {**os.environ}
        env["PYTHONPATH"] = get_pythonpath()
        result = subprocess.run(
            [sys.executable, "-m", "argus", "--help"],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0
        assert "Argus" in result.stdout
        assert "--help" in result.stdout

    def test_version_command(self):
        """Test that --version works."""
        env = {**os.environ}
        env["PYTHONPATH"] = get_pythonpath()
        result = subprocess.run(
            [sys.executable, "-m", "argus", "--version"],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0
        assert "0.1.0" in result.stdout

    def test_run_dry_run(self, monkeypatch):
        """Test dry-run mode loads config and prints settings."""
        # Set required env vars for config loading
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "test_chat")
        monkeypatch.setenv("TELEGRAM_PARSE_MODE", "MarkdownV2")
        monkeypatch.setenv("PYTHONPATH", get_pythonpath())

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "argus",
                "run",
                "--stream",
                "us_close_basic",
                "--mode",
                "us_close",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent),
            env={**os.environ, "PYTHONPATH": get_pythonpath()},
        )

        assert result.returncode == 0
        assert "=== Argus Dry Run ===" in result.stdout
        assert "Stream: us_close_basic" in result.stdout
        assert "Mode: us_close" in result.stdout
        assert "Configuration loaded" in result.stdout
        assert "Schedule:" in result.stdout

    def test_run_requires_mode(self):
        """Test that run command requires --mode."""
        env = {**os.environ}
        env["PYTHONPATH"] = get_pythonpath()
        result = subprocess.run(
            [sys.executable, "-m", "argus", "run", "--stream", "test"],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode != 0
        assert "Missing option" in result.stderr or "--mode" in result.stderr


class TestBinScript:
    """Tests for bin/argus script."""

    def test_bin_script_help(self):
        """Test that bin/argus --help works."""
        bin_path = Path(__file__).parent.parent / "bin" / "argus"
        if not bin_path.exists():
            pytest.skip("bin/argus not found")

        env = {**os.environ}
        env["PYTHONPATH"] = get_pythonpath()
        result = subprocess.run(
            [sys.executable, str(bin_path), "--help"],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0
        assert "Argus" in result.stdout
