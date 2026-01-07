# Task 15: Daemon Scheduler Mode

## Goal
Add a long-running daemon mode with internal scheduling, eliminating the need for external cron. The daemon handles all job scheduling internally with proper timezone support, health monitoring, and graceful recovery from downtime.

## Dependencies
- Task 13 (fixtures + docs/runbook)

## References
- `tasks/01_plan/spec.md` (Section 4: Scheduling & Timezones)
- `config.yaml` (schedule section)

---

## Background

### Current State
- CLI commands triggered by external cron
- Schedule config in `config.yaml` is informational only
- No long-running process capability

### Why Daemon Mode
| Aspect | External Cron | Daemon Mode |
|--------|---------------|-------------|
| Setup complexity | Manual crontab per job | Single systemd unit |
| Timezone handling | CRON_TZ (varies by system) | Built-in (APScheduler) |
| DST transitions | Manual verification | Automatic |
| Monitoring | Parse cron logs | Health endpoint |
| Config changes | Edit crontab + config | Just edit config, restart |

---

## Scope

### 1. Scheduler Core (`src/argus/daemon/scheduler.py`)

**Library:** APScheduler (AsyncIOScheduler)
- Mature, battle-tested
- First-class timezone support (critical for SGT + NY DST)
- Optional job persistence to database

**Scheduled Jobs:**

| Job | Schedule | Timezone | Notes |
|-----|----------|----------|-------|
| `ingest` | Every N minutes | UTC | From `rss.poll_interval_minutes` |
| `us_close` | Mon-Fri 06:00 | Asia/Singapore | Daily market update |
| `weekend_wrap` | Sat 10:00 | Asia/Singapore | Weekly recap |
| `monday_preview` | Sun 18:10 | America/New_York | Conditional on risk_score |
| `retention` | Daily 03:00 | UTC | Cleanup old data |

### 2. Persistence (`src/argus/daemon/persistence.py`)

**Store job state in PostgreSQL** (reuse existing DB):

```sql
CREATE TABLE scheduler_job_runs (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(50) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL,  -- 'running', 'success', 'failed'
    error_message TEXT,
    duration_ms INTEGER
);

CREATE INDEX idx_scheduler_job_runs_job_id ON scheduler_job_runs(job_id);
CREATE INDEX idx_scheduler_job_runs_started_at ON scheduler_job_runs(started_at);
```

**Tracks:**
- Last run time per job
- Success/failure status
- Run duration
- Error messages (if failed)

### 3. Missed Run Policy

**On daemon startup, check each job:**

| Job | If Missed | Rationale |
|-----|-----------|-----------|
| `ingest` | Run immediately | RSS feeds contain recent items; need them in DB |
| `retention` | Run immediately | Cleanup should happen |
| `us_close` | Skip, wait for next | Stale market update not useful |
| `weekend_wrap` | Skip, wait for next | Stale weekly recap not useful |
| `monday_preview` | Skip, wait for next | Stale preview not useful |

**News continuity after downtime:**
- RSS feeds retain items for 24-48h typically
- When ingestion runs after downtime, it fetches recent items (even from days ago if still in feed)
- Deduplication prevents duplicates
- Each item keeps its real `published_at` timestamp
- Next scheduled run queries correct time window → works correctly

**Example scenario:**
```
Mon 06:00 SGT - Daemon down, misses us_close
Tue 06:00 SGT - Still down, misses another
Wed 12:00 SGT - Daemon restarts
  → Ingestion runs immediately, fetches Mon/Tue/Wed news
  → us_close does NOT run (stale)
Thu 06:00 SGT - us_close runs normally
  → Queries last 24h window (Wed-Thu news)
  → Works correctly
```

### 4. Health Endpoint (`src/argus/daemon/health.py`)

**HTTP server** on configurable port (default 8080)

**Bind address:** `127.0.0.1` (localhost only for security)
- Access via SSH tunnel: `ssh -L 8080:localhost:8080 user@vps`
- Then: `curl http://localhost:8080/health`

**Endpoints:**

`GET /health`
```json
{
  "status": "healthy",
  "uptime_seconds": 86423,
  "version": "0.1.0",
  "jobs": {
    "ingest": {
      "enabled": true,
      "last_run": "2026-01-07T14:30:00Z",
      "last_status": "success",
      "next_run": "2026-01-07T14:40:00Z",
      "run_count": 144
    },
    "us_close": {
      "enabled": true,
      "last_run": "2026-01-07T22:00:00Z",
      "last_status": "success",
      "next_run": "2026-01-08T22:00:00Z",
      "run_count": 5
    },
    "weekend_wrap": {
      "enabled": true,
      "last_run": "2026-01-04T02:00:00Z",
      "last_status": "success",
      "next_run": "2026-01-11T02:00:00Z",
      "run_count": 1
    },
    "monday_preview": {
      "enabled": true,
      "last_run": null,
      "last_status": null,
      "next_run": "2026-01-11T23:10:00Z",
      "run_count": 0
    },
    "retention": {
      "enabled": true,
      "last_run": "2026-01-07T03:00:00Z",
      "last_status": "success",
      "next_run": "2026-01-08T03:00:00Z",
      "run_count": 7
    }
  }
}
```

`GET /health/jobs/{job_id}/history?limit=10`
```json
{
  "job_id": "us_close",
  "runs": [
    {
      "started_at": "2026-01-07T22:00:00Z",
      "completed_at": "2026-01-07T22:01:23Z",
      "status": "success",
      "duration_ms": 83000
    },
    ...
  ]
}
```

### 5. Signal Handling (`src/argus/daemon/signals.py`)

| Signal | Action |
|--------|--------|
| `SIGTERM` | Graceful shutdown: finish current job, then exit |
| `SIGINT` | Same as SIGTERM (Ctrl+C) |
| `SIGHUP` | (Future) Reload config without restart |

**Graceful shutdown flow:**
1. Stop accepting new jobs
2. Wait for currently running job to complete (with timeout)
3. Close database connections
4. Exit cleanly

### 6. CLI Commands

```bash
# Start daemon (foreground) - for testing/debugging
argus daemon start

# Start daemon (detached) - for production (or use systemd)
argus daemon start --detach

# Check status (queries health endpoint)
argus daemon status

# Manually trigger a job (for testing)
argus daemon trigger ingest
argus daemon trigger us_close --dry-run

# Stop daemon gracefully
argus daemon stop
```

### 7. Configuration

Add to `config.yaml`:

```yaml
daemon:
  enabled: true
  
  # Health endpoint
  health_port: 8080
  health_bind: "127.0.0.1"  # localhost only; use SSH tunnel
  
  # Logging
  log_file: null  # null = stdout (let systemd handle)
  log_level: INFO
  
  # Missed job policy (optional overrides)
  missed_policy:
    ingest: run_immediately
    retention: run_immediately
    us_close: skip
    weekend_wrap: skip
    monday_preview: skip
  
  # Job-specific overrides (optional)
  jobs:
    ingest:
      enabled: true
      # interval from rss.poll_interval_minutes
    us_close:
      enabled: true
    weekend_wrap:
      enabled: true
    monday_preview:
      enabled: true
    retention:
      enabled: true
      hour: 3  # UTC
```

### 8. Deployment Files

**systemd unit template** (`deploy/argus.service`):
```ini
[Unit]
Description=Argus Market Update Bot
After=network.target postgresql.service

[Service]
Type=simple
User=argus
Group=argus
WorkingDirectory=/opt/argus
ExecStart=/opt/argus/venv/bin/argus daemon start
ExecStop=/bin/kill -SIGTERM $MAINPID
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

# Security hardening
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=/opt/argus/logs

[Install]
WantedBy=multi-user.target
```

**Usage:**
```bash
sudo cp deploy/argus.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable argus
sudo systemctl start argus
sudo systemctl status argus
journalctl -u argus -f  # View logs
```

---

## File Structure

```
src/argus/daemon/
├── __init__.py
├── scheduler.py      # APScheduler setup, job definitions
├── persistence.py    # Job run history (PostgreSQL)
├── health.py         # HTTP health endpoint
├── signals.py        # SIGTERM/SIGINT handling
└── cli.py            # daemon subcommand handlers

deploy/
├── argus.service     # systemd unit file
└── README.md         # Deployment instructions
```

---

## Dependencies

Add to `pyproject.toml`:

```toml
dependencies = [
    # ... existing ...
    "apscheduler>=3.10,<4.0",
    "aiohttp>=3.9,<4.0",  # For health endpoint
]
```

---

## Acceptance Criteria

- [ ] `argus daemon start` runs continuously, executes scheduled jobs
- [ ] Jobs respect timezone (SGT for daily/weekend, NY for monday_preview)
- [ ] Health endpoint returns job status at `http://127.0.0.1:8080/health`
- [ ] Job run history persists to PostgreSQL
- [ ] Graceful shutdown (SIGTERM) completes current job before exit
- [ ] On restart: `ingest` and `retention` run if overdue; message runs skip
- [ ] systemd unit file works on Ubuntu 22.04+
- [ ] `argus daemon status` shows current job states
- [ ] `argus daemon trigger <job>` manually runs a job
- [ ] All existing tests still pass

---

## Testing

```bash
# Unit tests for scheduler logic
pytest tests/daemon/ -v

# Integration test: start daemon, verify health endpoint
argus daemon start &
sleep 5
curl http://localhost:8080/health
argus daemon stop

# Manual trigger test
argus daemon trigger ingest --dry-run
```

---

## Future Enhancements (Not in Scope)

- `SIGHUP` config reload without restart
- Prometheus `/metrics` endpoint
- Docker container support
- Web UI for job management
- Alerting on job failures (email/Slack/Telegram)
