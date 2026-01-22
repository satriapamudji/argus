# Daemon Skill

Manage the Argus systemd daemon.

## Usage

```
/daemon [command]
```

## Examples

- `/daemon status` - Check daemon status
- `/daemon restart` - Restart the daemon
- `/daemon logs` - Show recent logs

## Commands

### Check Status
```bash
systemctl status argus --no-pager
```

### Restart Daemon
```bash
sudo systemctl restart argus
```

### Stop Daemon
```bash
sudo systemctl stop argus
```

### Start Daemon
```bash
sudo systemctl start argus
```

### View Service Config
```bash
systemctl cat argus
```

### Check if Running
```bash
systemctl is-active argus
```

### Follow Logs
```bash
journalctl -u argus -f
```

## Health Endpoint

```bash
curl -s http://127.0.0.1:8080/health | python3 -m json.tool
```

## Daemon Configuration

From `config.yaml`:

```yaml
daemon:
  health_port: 8080
  health_bind: "127.0.0.1"
  retention_hour: 3  # Daily cleanup at 03:00 UTC
  health_ping_minutes: 30

  jobs_enabled:
    ingest: true
    us_close: true
    weekend_wrap: true
    monday_preview: true
    crypto_daily: true
    retention: true

  missed_policy:
    ingest: run_immediately
    retention: run_immediately
    us_close: skip
    weekend_wrap: skip
    monday_preview: skip
```

## Scheduled Jobs

| Job | Schedule | Missed Policy |
|-----|----------|---------------|
| ingest | Every 20 min | run_immediately |
| us_close | 22:00 UTC Mon-Fri | skip |
| weekend_wrap | 22:00 UTC Sat | skip |
| monday_preview | 12:00 UTC Mon | skip |
| crypto_daily | 00:00 UTC | skip |
| retention | 03:00 UTC | run_immediately |

## After Restart

On restart, the daemon will:
1. Run any `run_immediately` jobs that were missed (ingest, retention)
2. Skip any `skip` jobs that were missed (message jobs)
3. Schedule all future jobs normally

## Troubleshooting

### Daemon won't start
```bash
# Check for errors
journalctl -u argus -n 100 --no-pager

# Check service file
systemctl cat argus

# Try running manually
cd /opt/argus/app
source /opt/argus/.venv/bin/activate
python -m argus daemon start
```

### Health endpoint not responding
- Check if daemon is running: `systemctl is-active argus`
- Check port binding: `ss -tlnp | grep 8080`
- Check firewall rules
