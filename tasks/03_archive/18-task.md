# Task 17: Daemon Upgrades (journald heartbeat + structured logs)

## Goal
Improve VPS operability of the Argus daemon by:

- Adding a predictable **journald heartbeat** (liveness signal) every N minutes.
- Using `key=value` structured logs that are easy to filter with `journalctl`.
- Keeping logs **short when healthy** and **verbose only when degraded**.

## What Changed

### 1) Daemon heartbeat logging (`src/argus/daemon/scheduler.py`)
- Added a new internal interval job `health_ping` (APScheduler) controlled by config:
  - Logs once immediately at daemon start.
  - Then logs every `daemon.health_ping_minutes`.
- Healthy state:
  - Emits one INFO line:
    - `event=health_ping status=healthy uptime_s=... jobs_total=... jobs_enabled=... jobs_running=... degraded=0`
- Degraded/unhealthy state:
  - Emits one WARN/ERROR `event=health_ping ... degraded=1 ... degraded_jobs=...`
  - Emits per-job detail lines only for degraded jobs:
    - `event=job_health job_id=... enabled=... is_running=... last_status=... last_run=... next_run=... run_count=...`

### 2) Config support (`src/argus/config.py`, `config.yaml`)
- Added `daemon.health_ping_minutes` with default `10`.
- Setting `health_ping_minutes <= 0` disables scheduling the heartbeat.

### 3) Bug fix: avoid unnecessary DB work in `get_status()`
- Removed an unused call that opened a DB connection (`get_running_jobs(get_connection())`) without closing it.
- Keeps heartbeat safer by avoiding extra DB load/leaks.

### 4) Tests (`tests/test_daemon.py`)
- Added coverage for:
  - default `health_ping_minutes == 10`
  - YAML override for `health_ping_minutes`

### 5) Ops docs (`docs/OPERATIONS.md`)
- Added `health_ping_minutes` to daemon config example.
- Added `journalctl`/grep examples to filter heartbeats and warnings.

## Files Modified
- `src/argus/daemon/scheduler.py`
- `src/argus/config.py`
- `config.yaml`
- `tests/test_daemon.py`
- `docs/OPERATIONS.md`

## Acceptance Criteria
- Daemon logs one heartbeat line immediately on startup.
- Daemon logs one heartbeat line every 10 minutes by default.
- Healthy case remains low-noise (one line only).
- Degraded case provides extra per-job detail lines (only when needed).
- Test suite passes.

## Testing Evidence
- `pytest -q`: 487 passed, 5 skipped (1 warning: unknown pytest mark `db`, pre-existing)
