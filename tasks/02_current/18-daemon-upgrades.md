# 18 — Daemon Upgrades (journald logging + health heartbeat)

## Goal
Improve VPS operability for the **Argus Market Update Daemon** (systemd + journald) by:

1) Making daemon/job behavior **observable from `journalctl`** without needing external probes.
2) Adding a predictable **liveness signal** via a periodic health heartbeat log.
3) Keeping logs **short when healthy**, and **detailed only when degraded**.

This is explicitly targeted at VPS deployment where operators rely on:

- `systemctl status argus`
- `journalctl -u argus -f`
- occasional `/health` checks (SSH tunnel / localhost)

Non-goal: introduce new monitoring systems (Prometheus, external uptime services) as part of this change.

---

## Current State (as of today)

- systemd unit exists at `deploy/argus.service`.
  - stdout/stderr go to journald:
    - `StandardOutput=journal`
    - `StandardError=journal`
    - `SyslogIdentifier=argus`
- Daemon runs via:
  - `argus daemon start --config /opt/argus/config.yaml`
- Health endpoint exists (aiohttp):
  - `GET /health` returns overall daemon status and job info
  - `GET /health/jobs/{job_id}/history` returns recent run history

Gap: journald does not reliably show liveness during quiet periods; health is available but not periodically surfaced in logs.

---

## Proposed Logging Standard

### Structured `key=value` format
All new daemon ops logs should be single-line `key=value` pairs.

Rationale:
- Easy to grep/filter in `journalctl` output.
- Stable keys support lightweight log-based alerting later.

Examples:

Healthy heartbeat (INFO):
```
event=health_ping status=healthy uptime_s=3720 jobs_total=5 jobs_enabled=5 jobs_running=0 degraded=0
```

Degraded heartbeat (WARN/ERROR) + per-job detail lines (only when degraded):
```
event=health_ping status=degraded uptime_s=3720 jobs_total=5 jobs_enabled=5 jobs_running=0 degraded=1 degraded_jobs=us_close
event=job_health job_id=us_close enabled=1 is_running=0 last_status=error last_run=2026-01-08T01:23:45Z next_run=2026-01-08T06:00:00+08:00 run_count=42
```

### Keys (stable schema)
Heartbeat keys (always present):
- `event=health_ping`
- `status=healthy|degraded|unhealthy`
- `uptime_s=<int>`
- `jobs_total=<int>`
- `jobs_enabled=<int>`
- `jobs_running=<int>`
- `degraded=0|1`

Degraded-only additions:
- `degraded_jobs=<comma-separated job ids>`

Per-job degraded-only detail keys:
- `event=job_health`
- `job_id=<id>`
- `enabled=0|1`
- `is_running=0|1`
- `last_status=<string|null>`
- `last_run=<iso8601|null>`
- `next_run=<iso8601|null>`
- `run_count=<int>`

---

## Heartbeat Requirements

- Frequency: **every 10 minutes**
- Behavior: **log once immediately on startup**, then every 10 minutes
- Healthy case: exactly **one line** per heartbeat interval
- Degraded case:
  - one WARN/ERROR heartbeat line
  - plus one `event=job_health` line per degraded job

---

## Configuration Changes

Add to `config.yaml`:

```yaml
daemon:
  # ... existing daemon settings ...
  health_ping_minutes: 10  # 0 disables heartbeat
```

Add to `DaemonConfig` (`src/argus/config.py`):
- `health_ping_minutes: int = 10`

Parsing:
- load `daemon.health_ping_minutes` from YAML
- treat `<= 0` as disabled

---

## Implementation Plan (Engineering Steps)

### 1) Extend configuration model
Files:
- `src/argus/config.py`

Steps:
- Add `health_ping_minutes` to `DaemonConfig` with default `10`.
- Parse `health_ping_minutes` in `ArgusConfig.load` from YAML `daemon` block.

### 2) Update default config example
Files:
- `config.yaml`

Steps:
- Add `daemon.health_ping_minutes: 10`.

### 3) Add heartbeat job to daemon scheduler
Files:
- `src/argus/daemon/scheduler.py`

Steps:
- Add a new internal scheduled task (APScheduler interval) that calls a method like `_log_health_ping()`.
- Schedule it iff `health_ping_minutes > 0`.
- Emit one immediate heartbeat after daemon startup (before waiting for shutdown), then rely on the scheduler for periodic heartbeats.

Heartbeat logic:
- Call `self.get_status()`.
- Compute `uptime_s` from `started_at`.
- Derive `jobs_total`, `jobs_enabled`, `jobs_running` from status/jobs.
- Determine degraded jobs:
  - any enabled job with `last_status == "error"` (and/or daemon overall status != healthy)
  - (optional later) detect “stuck running too long” with a threshold
- Logging:
  - healthy: INFO single-line heartbeat
  - degraded/unhealthy: WARN/ERROR heartbeat + per-job `event=job_health` lines

### 4) Add/adjust tests
Files:
- `tests/test_daemon.py`

Steps:
- Add assertion that `DaemonConfig().health_ping_minutes == 10`.
- Add YAML load test coverage for overriding `health_ping_minutes`.

---

## Operational Verification (VPS)

Commands:

- Follow logs:
  - `journalctl -u argus -f`
- Filter heartbeats:
  - `journalctl -u argus | grep "event=health_ping"`
- Surface degraded conditions:
  - `journalctl -u argus -p warning`

Expected:
- You see an immediate `event=health_ping ...` after service start.
- You see repeating heartbeat lines every ~10 minutes.
- When degraded, you see WARN/ERROR heartbeat + `event=job_health` lines; when healthy, you do not.

---

## Notes / Follow-ups (Optional)

- If you later want the daemon to actually be restarted on hang, consider systemd watchdog (`Type=notify` + `WatchdogSec=` + sd_notify). Not included in this plan.
- If you want dependency checks (DB connectivity) on heartbeat, add a short-timeout DB probe and include `db_ok=0|1` keys. Not included in v1.
