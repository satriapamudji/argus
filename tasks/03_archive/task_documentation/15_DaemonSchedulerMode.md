# Task 15: Daemon Scheduler Mode

## Summary
Implemented a long-running daemon mode with internal scheduling using APScheduler, eliminating the need for external cron configuration. Suitable for VPS deployment with built-in health monitoring, graceful shutdown, and missed job handling.

## What Was Before
- Argus relied entirely on external cron for scheduling (Linux) or Task Scheduler (Windows)
- No way to monitor job status without checking logs
- No built-in health endpoint for monitoring
- Job history only tracked in runs table for message jobs
- Complex cron configuration required for timezone handling

## What Changed

### 1. Daemon Module (`src/argus/daemon/`)

Created a new module for long-running daemon functionality:

| File | Purpose |
|------|---------|
| `__init__.py` | Module exports (`ArgusDaemon`) |
| `types.py` | Dataclasses: `JobRunRecord`, `JobStatus`, `DaemonStatus` |
| `persistence.py` | Database operations for job run history |
| `signals.py` | `SignalHandler` for SIGTERM/SIGINT graceful shutdown |
| `health.py` | HTTP health server with aiohttp |
| `scheduler.py` | `ArgusDaemon` class with APScheduler integration |

### 2. Scheduled Jobs

| Job ID | Schedule | Timezone | Description |
|--------|----------|----------|-------------|
| `ingest` | Every N minutes | - | RSS feed polling (interval from config) |
| `us_close` | Mon-Fri 06:00 | Asia/Singapore | Daily US close market update |
| `weekend_wrap` | Sat 10:00 | Asia/Singapore | Weekend wrap summary |
| `monday_preview` | Sun 18:10 | America/New_York | Monday preview (DST-safe) |
| `retention` | Daily 03:00 | UTC | Database retention cleanup |

### 3. Health Endpoint

HTTP server on `127.0.0.1:8080` (localhost only for security):

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Overall daemon status and job info |
| `/health/jobs/{job_id}/history` | GET | Recent run history for a job |
| `/trigger/{job_id}` | POST | Manually trigger a job |

Example response:
```json
{
  "status": "healthy",
  "uptime_seconds": 3600,
  "version": "0.1.0",
  "jobs": {
    "ingest": {
      "enabled": true,
      "last_status": "success",
      "next_run": "2025-01-07T13:00:00Z",
      "run_count": 42
    }
  }
}
```

### 4. CLI Commands (`src/argus/cli.py`)

Added new daemon command group:

```bash
# Start daemon in foreground
argus daemon start

# Check status (queries health endpoint)
argus daemon status

# Manually trigger a job
argus daemon trigger ingest

# View job history
argus daemon history us_close --limit 20
```

### 5. Configuration (`config.yaml`)

Added daemon section:

```yaml
daemon:
  health_port: 8080
  health_bind: "127.0.0.1"
  retention_hour: 3

  jobs_enabled:
    ingest: true
    us_close: true
    weekend_wrap: true
    monday_preview: true
    retention: true

  missed_policy:
    ingest: run_immediately
    retention: run_immediately
    us_close: skip
    weekend_wrap: skip
    monday_preview: skip
```

### 6. Database Migration

Created `003_scheduler_job_runs.sql`:

```sql
CREATE TABLE scheduler_job_runs (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(50) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    error_message TEXT,
    duration_ms INTEGER,
    run_id INTEGER REFERENCES runs(id),
    trigger_type VARCHAR(20) NOT NULL DEFAULT 'scheduled'
);
```

### 7. systemd Service File

Created `deploy/argus.service` for production deployment:

```ini
[Unit]
Description=Argus Market Update Daemon
After=network.target postgresql.service

[Service]
Type=simple
User=argus
ExecStart=/opt/argus/.venv/bin/argus daemon start
Restart=always
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

### 8. Documentation Updates

**`docs/OPERATIONS.md`**: Added comprehensive daemon deployment section including:
- Architecture diagram
- Quick start guide
- Configuration reference
- systemd setup instructions
- Health endpoint usage
- Remote monitoring via SSH tunnel
- Graceful shutdown behavior
- Missed job handling policies

**`README.md`**: Added daemon commands table and usage example.

## Files Created/Modified

| File | Change |
|------|--------|
| `pyproject.toml` | **Modified** - Added `apscheduler>=3.10,<4.0`, `aiohttp>=3.9,<4.0` |
| `src/argus/daemon/__init__.py` | **Created** - Module exports |
| `src/argus/daemon/types.py` | **Created** - Dataclass definitions |
| `src/argus/daemon/persistence.py` | **Created** - DB operations (~120 lines) |
| `src/argus/daemon/signals.py` | **Created** - Signal handling (~60 lines) |
| `src/argus/daemon/health.py` | **Created** - HTTP server (~220 lines) |
| `src/argus/daemon/scheduler.py` | **Created** - Daemon core (~520 lines) |
| `src/argus/config.py` | **Modified** - Added `DaemonConfig` dataclass |
| `src/argus/cli.py` | **Modified** - Added ~300 lines for daemon commands |
| `src/argus/db/migrations/003_scheduler_job_runs.sql` | **Created** - Migration |
| `config.yaml` | **Modified** - Added daemon section |
| `deploy/argus.service` | **Created** - systemd unit file |
| `docs/OPERATIONS.md` | **Modified** - Added daemon deployment guide (~200 lines) |
| `README.md` | **Modified** - Added daemon section |
| `tests/test_daemon.py` | **Created** - Unit tests (~250 lines) |

## Key Features

### Graceful Shutdown
When receiving SIGTERM/SIGINT:
1. Stops accepting new scheduled jobs
2. Waits up to 30 seconds for running jobs to complete
3. Cleans up resources and exits

### Missed Job Handling
On daemon startup, checks for jobs that were missed during downtime:

| Policy | Behavior | Used By |
|--------|----------|---------|
| `run_immediately` | Trigger job right away | `ingest`, `retention` |
| `skip` | Wait for next scheduled run | `us_close`, `weekend_wrap`, `monday_preview` |

This prevents sending stale market updates while ensuring ingestion catches up quickly.

### Job Run History
All job executions are recorded in `scheduler_job_runs` table:
- Started/completed timestamps
- Status (running/success/failed)
- Duration in milliseconds
- Error messages for failures
- Trigger type (scheduled/manual/catchup)
- Link to runs table for message jobs

## Reasoning

From `tasks/01_plan/15-task.md`:
> "For a £5/mo VPS, external cron is fragile and hard to monitor. A daemon with internal scheduler is more robust."

The daemon approach provides:
1. **Simplified deployment**: Single systemd service instead of multiple cron entries
2. **Better monitoring**: Built-in health endpoint with job status
3. **Missed job handling**: Configurable catch-up policies
4. **Graceful shutdown**: Waits for running jobs to complete
5. **Centralized logging**: All jobs log through one process

## Acceptance Criteria Status

| Criterion | Status |
|-----------|--------|
| APScheduler-based internal scheduler | Done |
| All 5 job types scheduled (ingest, us_close, weekend_wrap, monday_preview, retention) | Done |
| Timezone-aware scheduling (SGT, NY, UTC) | Done |
| Health endpoint for monitoring | Done |
| Graceful shutdown with SIGTERM/SIGINT | Done |
| Job run history persistence | Done |
| CLI commands (start/status/trigger/history) | Done |
| Missed job catch-up policies | Done |
| systemd service file | Done |
| Documentation updated | Done |
| Unit tests | Done |

## Test Results

- All 425 tests pass (14 new daemon tests + 1 skipped for DB requirement)
- pyright: No errors
- CLI commands verified working:
  - `argus daemon --help` - Shows subcommands
  - `argus daemon start --help` - Shows options
