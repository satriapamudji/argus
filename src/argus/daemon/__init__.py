"""Daemon scheduler module for Argus.

This module provides a long-running daemon mode with internal scheduling,
eliminating the need for external cron. The daemon handles:

- Scheduled job execution (ingest, us_close, weekend_wrap, monday_preview, retention)
- Timezone-aware scheduling (SGT for daily/weekend, NY for monday_preview)
- Health endpoint for monitoring
- Graceful shutdown handling
- Job run history persistence

Usage:
    argus daemon start          # Run as foreground daemon
    argus daemon status         # Check daemon status
    argus daemon trigger ingest # Manually trigger a job
"""

from argus.daemon.scheduler import ArgusDaemon

__all__ = ["ArgusDaemon"]
