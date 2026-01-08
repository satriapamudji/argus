# Daemon Heartbeat (journald) — Implementation Notes

## Overview
This update adds a lightweight, journald-friendly liveness signal for the Argus daemon.

Instead of requiring operators to curl `/health` or wait for the next scheduled job, the daemon now emits an INFO heartbeat periodically.

## Configuration
In `config.yaml`:

```yaml
daemon:
  health_ping_minutes: 10  # Journald heartbeat interval (0 to disable)
```

- Default: `10`
- Disable: set `0` (or any `<= 0`)

## Logging Format
All heartbeat-related logs follow a `key=value` single-line format.

### Healthy heartbeat
- One INFO line per interval

Example:
```
event=health_ping status=healthy uptime_s=3720 jobs_total=5 jobs_enabled=5 jobs_running=0 degraded=0
```

### Degraded heartbeat
- One WARN line per interval when degraded
- Additional per-job lines only for degraded jobs

Example:
```
event=health_ping status=degraded uptime_s=3720 jobs_total=5 jobs_enabled=5 jobs_running=0 degraded=1 degraded_jobs=us_close
event=job_health job_id=us_close enabled=1 is_running=0 last_status=failed last_run=2026-01-08T01:23:45Z next_run=2026-01-08T06:00:00+08:00 run_count=42
```

## Implementation Details
- Scheduling is done via APScheduler in `src/argus/daemon/scheduler.py`.
- Behavior:
  - Log one immediate heartbeat after daemon startup.
  - If enabled, schedule interval job `health_ping` to emit subsequent heartbeats.

### Degraded detection
- `degraded_jobs` are currently defined as enabled jobs whose last persisted status is `failed`.
- Daemon-level `status` is considered degraded if any job is failed.

## Operations / Debugging
Useful commands:

- Follow logs:
  - `journalctl -u argus -f`
- Show only heartbeats:
  - `journalctl -u argus | grep "event=health_ping"`
- Show degraded/unhealthy signals:
  - `journalctl -u argus -p warning`
