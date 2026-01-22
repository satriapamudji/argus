# Logs Skill

Check Argus daemon logs from journalctl.

## Usage

```
/logs [filter]
```

## Examples

- `/logs` - Show recent logs
- `/logs crypto` - Filter for crypto-related entries
- `/logs errors` - Show errors and failures
- `/logs today` - Show today's logs

## Commands

### Recent logs (last 50 lines)
```bash
journalctl -u argus -n 50 --no-pager
```

### Today's logs
```bash
journalctl -u argus --since today --no-pager
```

### Errors and failures only
```bash
journalctl -u argus --since today 2>/dev/null | grep -iE "error|fail|exception|traceback" | tail -50
```

### Crypto stream logs
```bash
journalctl -u argus --since today 2>/dev/null | grep -iE "crypto|bitcoin|btc|eth" | tail -30
```

### Follow logs in real-time
```bash
journalctl -u argus -f
```

### Specific time range
```bash
journalctl -u argus --since "2026-01-22 00:00" --until "2026-01-22 01:00" --no-pager
```

### Check daemon status
```bash
systemctl status argus
```

## Log Patterns to Watch For

| Pattern | Meaning |
|---------|---------|
| `Bundle validation failed` | Schema validation error in facts bundle |
| `Validation failed (attempt N/5)` | LLM output failed validation, retrying |
| `Run failed` | Orchestrator run failed |
| `newspaper4k extracted insufficient` | Content extraction warning (usually OK) |
| `Telegram getUpdates failed` | Telegram polling error (usually transient) |

## Important Notes

1. Argus runs as systemd service: `argus.service`
2. Logs go to journald, not files
3. Daemon restarts clear in-memory state but jobs catch up via `missed_policy`
4. Health endpoint: `http://127.0.0.1:8080/health`
