"""Tests that the CLI can print the final generated message.

This is an offline-ish test: we stub RunOrchestrator.run() to avoid DB/network.
"""

import os
import subprocess
import sys
from pathlib import Path


def get_pythonpath() -> str:
    """Get PYTHONPATH with src directory included."""
    return str(Path(__file__).parent.parent / "src")


def test_run_prints_message_when_enabled(monkeypatch):
    """--print-message prints RunResult.message_content."""
    monkeypatch.setenv("PYTHONPATH", get_pythonpath())

    stub = (
        "from argus.orchestrator.types import RunResult, RunStatus\n"
        "from argus.orchestrator import RunOrchestrator\n"
        "def _stub_run(self, now=None):\n"
        "    r = RunResult(status=RunStatus.COMPLETED, run_id=1, message_id=2)\n"
        "    r.message_content = 'hello from stub'\n"
        "    return r\n"
        "RunOrchestrator.run = _stub_run\n"
    )

    cmd = [
        sys.executable,
        "-c",
        f"{stub}"
        "import sys as _sys; from argus.cli import cli as _cli; _sys.argv=['argus','run','--stream','us_markets','--mode','us_close','--skip-publish','--print-message']; _cli()",
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent),
        env={**os.environ, "PYTHONPATH": get_pythonpath()},
    )

    assert result.returncode == 0
    assert "--- FINAL GENERATED MESSAGE ---" in result.stdout
    assert "hello from stub" in result.stdout
    assert "--- END MESSAGE ---" in result.stdout
