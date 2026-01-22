# Status Skill

Check overall Argus system status.

## Usage

```
/status
```

## Quick Status Commands

### Daemon Status
```bash
systemctl status argus --no-pager
```

### Health Check
```bash
curl -s http://127.0.0.1:8080/health | python3 -m json.tool
```

### Recent Runs (All Streams)
```bash
source /opt/argus/.venv/bin/activate
python3 scripts/dbquery.py --runs 10
```

### News Stats
```bash
source /opt/argus/.venv/bin/activate
python3 scripts/dbquery.py --stats
```

### Partition Count
```bash
source /opt/argus/.venv/bin/activate
python3 scripts/dbquery.py --partitions
```

## Full Status Check Script

```bash
echo "=== DAEMON STATUS ==="
systemctl is-active argus

echo -e "\n=== HEALTH ENDPOINT ==="
curl -s http://127.0.0.1:8080/health 2>/dev/null || echo "Health endpoint not responding"

echo -e "\n=== RECENT RUNS ==="
source /opt/argus/.venv/bin/activate
python3 /opt/argus/app/scripts/dbquery.py --runs 5

echo -e "\n=== NEWS STATS ==="
python3 /opt/argus/app/scripts/dbquery.py --stats
```

## Stream Schedules

| Stream | Job | Schedule (UTC) |
|--------|-----|----------------|
| us_markets | us_close | 22:00 Mon-Fri |
| us_markets | weekend_wrap | 22:00 Sat |
| us_markets | monday_preview | 12:00 Mon |
| crypto | crypto_daily | 00:00 daily |
| all | ingest | Every 20 min |
| all | retention | 03:00 daily |

## Service Management

```bash
# Restart daemon
sudo systemctl restart argus

# Stop daemon
sudo systemctl stop argus

# View full service config
systemctl cat argus
```

## Config Location

- Main config: `/opt/argus/app/config.yaml`
- Environment: `/opt/argus/app/.env`
- Venv: `/opt/argus/.venv`

## Key Metrics to Watch

| Metric | Good | Bad |
|--------|------|-----|
| Daemon status | active (running) | inactive/failed |
| Recent runs | completed | failed |
| News items | Growing daily | Stale dates |
| Partitions | Daily partitions created | Missing days |
