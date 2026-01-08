# Argus Operations Guide

This document provides detailed instructions for deploying and operating Argus in production (Linux VPS) and development (Windows) environments.

## Table of Contents

1. [Deployment Overview](#deployment-overview)
2. [Daemon Mode Deployment (Recommended)](#daemon-mode-deployment-recommended)
3. [Linux VPS Deployment (Cron-based)](#linux-vps-deployment)
4. [Windows Development Setup](#windows-development-setup)
5. [Database Operations](#database-operations)
6. [Retention Management](#retention-management)
7. [Monitoring and Logging](#monitoring-and-logging)
8. [Troubleshooting](#troubleshooting)

---

## Deployment Overview

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              VPS / Server                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────────────────┐   │
│  │   Cron      │     │   Argus     │     │      PostgreSQL         │   │
│  │  Scheduler  │ ──▶ │   Python    │ ──▶ │      Database           │   │
│  └─────────────┘     └─────────────┘     └─────────────────────────┘   │
│                             │                                           │
│                             ▼                                           │
│                      ┌─────────────┐     ┌─────────────────────────┐   │
│                      │  OpenRouter │     │       Telegram          │   │
│                      │  (LLM API)  │     │       Bot API           │   │
│                      └─────────────┘     └─────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Schedule Summary

| Job | Schedule | Timezone | Command |
|-----|----------|----------|---------|
| Daily US Close | Mon-Fri 06:00 | Asia/Singapore | `argus run --mode us_close` |
| Weekend Wrap | Sat 10:00 | Asia/Singapore | `argus run --mode weekend_wrap` |
| Monday Preview | Sun 18:10 | America/New_York | `argus run --mode monday_preview --conditional` |
| RSS Ingestion | Every 10 min | Any | `argus ingest` |
| Retention Cleanup | Daily 03:00 | Asia/Singapore | `argus db cleanup` |
| Partition Creation | Weekly Sun 04:00 | Asia/Singapore | `argus db create-partitions --days 14` |

---

## Daemon Mode Deployment (Recommended)

Daemon mode is the recommended deployment method for VPS environments. It uses a long-running process with internal scheduling (APScheduler), eliminating the need for external cron configuration.

### Benefits

- **Simpler setup**: One systemd service instead of multiple cron entries
- **Better monitoring**: Built-in health endpoint with job status
- **Missed job handling**: Configurable catch-up policies for jobs missed during downtime
- **Graceful shutdown**: Waits for running jobs to complete
- **Centralized logging**: All jobs log through the daemon process

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              VPS / Server                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐     ┌─────────────────────────────────────────────┐   │
│  │   systemd   │     │              Argus Daemon                    │   │
│  │   Service   │ ──▶ │  ┌─────────────────────────────────────┐    │   │
│  └─────────────┘     │  │          APScheduler                 │    │   │
│                      │  │  - ingest (every 10 min)             │    │   │
│                      │  │  - us_close (Mon-Fri 06:00 SGT)      │    │   │
│                      │  │  - weekend_wrap (Sat 10:00 SGT)      │    │   │
│                      │  │  - monday_preview (Sun 18:10 NY)     │    │   │
│                      │  │  - retention (daily 03:00 UTC)       │    │   │
│                      │  └─────────────────────────────────────┘    │   │
│                      │                     │                        │   │
│                      │  ┌──────────────────┼──────────────────┐    │   │
│                      │  │ Health Server    │                  │    │   │
│                      │  │ :8080/health     ▼                  │    │   │
│                      │  └─────────────────────────────────────┘    │   │
│                      └─────────────────────────────────────────────┘   │
│                             │                                           │
│                             ▼                                           │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────────────────┐   │
│  │ PostgreSQL  │     │  OpenRouter │     │       Telegram          │   │
│  │  Database   │     │  (LLM API)  │     │       Bot API           │   │
│  └─────────────┘     └─────────────┘     └─────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Quick Start

```bash
# Start daemon in foreground (for testing)
argus daemon start

# Check daemon status (in another terminal)
argus daemon status

# Manually trigger a job
argus daemon trigger ingest

# View job history
argus daemon history us_close
```

### Step 1: Configure Daemon

Add daemon section to `config.yaml`:

```yaml
daemon:
  health_port: 8080
  health_bind: "127.0.0.1"  # Localhost only - access via SSH tunnel
  retention_hour: 3  # Daily retention cleanup at 03:00 UTC
  health_ping_minutes: 10  # Journald heartbeat interval (0 to disable)

  # Enable/disable individual jobs
  jobs_enabled:
    ingest: true
    us_close: true
    weekend_wrap: true
    monday_preview: true
    retention: true

  # Missed job policy: 'run_immediately' or 'skip'
  missed_policy:
    ingest: run_immediately  # Always catch up on ingestion
    retention: run_immediately  # Always catch up on cleanup
    us_close: skip  # Don't send stale market updates
    weekend_wrap: skip  # Don't send stale weekend wraps
    monday_preview: skip  # Don't send stale monday previews
```

### Step 2: Install systemd Service

```bash
# Copy service file
sudo cp /opt/argus/deploy/argus.service /etc/systemd/system/

# Edit paths if needed
sudo nano /etc/systemd/system/argus.service

# Reload systemd
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable argus

# Start the daemon
sudo systemctl start argus

# Check status
sudo systemctl status argus
```

### Step 3: Verify Deployment

```bash
# Check service is running
sudo systemctl status argus

# View logs
sudo journalctl -u argus -f

# Filter daemon heartbeat (liveness)
sudo journalctl -u argus | grep "event=health_ping"

# Show only degraded/unhealthy signals
sudo journalctl -u argus -p warning

# Check health endpoint (via SSH tunnel or locally)
curl http://127.0.0.1:8080/health

# Check job status
argus daemon status
```

### Daemon CLI Commands

| Command | Description |
|---------|-------------|
| `argus daemon start` | Run daemon in foreground |
| `argus daemon status` | Show daemon and job status |
| `argus daemon trigger <job>` | Manually trigger a job |
| `argus daemon history <job>` | Show recent run history for a job |

### Health Endpoint

The daemon exposes an HTTP health endpoint on `127.0.0.1:8080` (localhost only for security).

#### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Overall daemon status and job info |
| `/health/jobs/{job_id}/history` | GET | Recent run history for a job |
| `/trigger/{job_id}` | POST | Manually trigger a job |

#### Example Health Response

```json
{
  "status": "healthy",
  "uptime_seconds": 3600,
  "version": "0.1.0",
  "started_at": "2025-01-07T12:00:00Z",
  "jobs": {
    "ingest": {
      "enabled": true,
      "last_run": "2025-01-07T12:50:00Z",
      "last_status": "success",
      "next_run": "2025-01-07T13:00:00Z",
      "run_count": 42,
      "is_running": false
    },
    "us_close": {
      "enabled": true,
      "last_run": "2025-01-07T06:00:00Z",
      "last_status": "success",
      "next_run": "2025-01-08T06:00:00Z",
      "run_count": 5,
      "is_running": false
    }
  }
}
```

### Remote Monitoring

Since the health endpoint binds to localhost only, access it via SSH tunnel:

```bash
# Create SSH tunnel (run on your local machine)
ssh -L 8080:127.0.0.1:8080 user@your-vps

# Then access locally
curl http://localhost:8080/health
```

Or use `argus daemon status` directly on the server.

### Graceful Shutdown

When stopped (via `systemctl stop argus` or SIGTERM):

1. Daemon stops accepting new scheduled jobs
2. Waits up to 30 seconds for running jobs to complete
3. Cleans up resources and exits

### Missed Job Handling

When the daemon starts, it checks for jobs that were missed during downtime:

| Policy | Behavior |
|--------|----------|
| `run_immediately` | Trigger the job right away (for ingest, retention) |
| `skip` | Wait for next scheduled run (for message jobs) |

This prevents sending stale market updates while ensuring ingestion catches up quickly.

---

## Linux VPS Deployment (Cron-based)

### Prerequisites

- Ubuntu 22.04+ or Debian 12+ (recommended)
- Python 3.12+
- PostgreSQL 14+
- System cron (cronie or systemd-cron)

### Step 1: System Preparation

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.12
sudo apt install -y python3.12 python3.12-venv python3.12-dev

# Install PostgreSQL
sudo apt install -y postgresql postgresql-contrib

# Install build dependencies
sudo apt install -y build-essential libpq-dev
```

### Step 2: Create Application User

```bash
# Create dedicated user
sudo useradd -m -s /bin/bash argus
sudo passwd argus

# Switch to argus user
sudo su - argus
```

### Step 3: Install Argus

```bash
# Clone repository
cd /home/argus
git clone https://github.com/your-org/argus.git
cd argus

# Create virtual environment
python3.12 -m venv venv
source venv/bin/activate

# Install package
pip install --upgrade pip
pip install -e .

# Verify installation
argus --version
argus smoke
```

### Step 4: Configure Environment

```bash
# Create .env file
cat > /home/argus/argus/.env << 'EOF'
# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
TELEGRAM_PARSE_MODE=MarkdownV2

# Database
DATABASE_URL=postgresql://argus:your_password@localhost:5432/argus

# LLM
OPENROUTER_API_KEY=sk-or-v1-your_key_here

# Logging
LOG_LEVEL=INFO
EOF

# Secure the file
chmod 600 /home/argus/argus/.env
```

### Step 5: Configure PostgreSQL

```bash
# Switch to postgres user
sudo -u postgres psql

# Create database and user
CREATE USER argus WITH PASSWORD 'your_secure_password';
CREATE DATABASE argus OWNER argus;
GRANT ALL PRIVILEGES ON DATABASE argus TO argus;
\q
```

```bash
# Run migrations
source /home/argus/argus/venv/bin/activate
cd /home/argus/argus
argus db migrate

# Create initial partitions
argus db create-partitions --days 14
```

### Step 6: Configure Cron Jobs

Create the cron configuration file:

```bash
sudo nano /etc/cron.d/argus
```

Add the following content:

```cron
# Argus Market Update Bot - Cron Configuration
# =============================================

# Environment
SHELL=/bin/bash
PATH=/home/argus/argus/venv/bin:/usr/local/bin:/usr/bin:/bin
ARGUS_HOME=/home/argus/argus

# Activate venv and cd to project for each job
# Format: minute hour day month weekday user command

# -----------------------------------------------------------------------------
# SGT Timezone Jobs (Asia/Singapore)
# -----------------------------------------------------------------------------
CRON_TZ=Asia/Singapore

# Daily US Close Update - Mon-Fri 06:00 SGT
0 6 * * 1-5 argus cd $ARGUS_HOME && source venv/bin/activate && argus run --stream us_close_basic --mode us_close >> /var/log/argus/us_close.log 2>&1

# Weekend Wrap - Sat 10:00 SGT
0 10 * * 6 argus cd $ARGUS_HOME && source venv/bin/activate && argus run --stream us_close_basic --mode weekend_wrap >> /var/log/argus/weekend_wrap.log 2>&1

# Retention Cleanup - Daily 03:00 SGT
0 3 * * * argus cd $ARGUS_HOME && source venv/bin/activate && argus db cleanup >> /var/log/argus/cleanup.log 2>&1

# Partition Creation - Weekly Sunday 04:00 SGT
0 4 * * 0 argus cd $ARGUS_HOME && source venv/bin/activate && argus db create-partitions --days 14 >> /var/log/argus/partitions.log 2>&1

# -----------------------------------------------------------------------------
# NY Timezone Jobs (America/New_York) - DST-Safe
# -----------------------------------------------------------------------------
CRON_TZ=America/New_York

# Monday Preview - Sun 18:10 NY (10 min after futures open)
10 18 * * 0 argus cd $ARGUS_HOME && source venv/bin/activate && argus run --stream us_close_basic --mode monday_preview --conditional >> /var/log/argus/monday_preview.log 2>&1

# -----------------------------------------------------------------------------
# Ingestion (runs frequently, any timezone)
# -----------------------------------------------------------------------------
CRON_TZ=UTC

# RSS Ingestion - Every 10 minutes
*/10 * * * * argus cd $ARGUS_HOME && source venv/bin/activate && argus ingest >> /var/log/argus/ingest.log 2>&1

# Economic Calendar Refresh - Every 6 hours
0 */6 * * * argus cd $ARGUS_HOME && source venv/bin/activate && argus calendar refresh >> /var/log/argus/calendar.log 2>&1
```

Create log directory:

```bash
sudo mkdir -p /var/log/argus
sudo chown argus:argus /var/log/argus
```

Set permissions and reload cron:

```bash
sudo chmod 644 /etc/cron.d/argus
sudo systemctl restart cron
```

### Step 7: Log Rotation

Create logrotate configuration:

```bash
sudo nano /etc/logrotate.d/argus
```

```
/var/log/argus/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 644 argus argus
}
```

### Step 8: Verify Deployment

```bash
# Check cron jobs are scheduled
sudo crontab -u argus -l

# Run a dry-run test
cd /home/argus/argus
source venv/bin/activate
argus run --stream us_close_basic --mode us_close --dry-run

# Run smoke test
argus smoke --verbose

# Manually trigger ingestion
argus ingest --dry-run
```

---

## Windows Development Setup

### Prerequisites

- Windows 10/11
- Python 3.12+ (from [python.org](https://www.python.org/downloads/) or `winget install Python.Python.3.12`)
- PostgreSQL 14+ (or Docker)
- Git

### Step 1: Install Python

```powershell
# Option A: Using winget
winget install Python.Python.3.12

# Option B: Download from python.org
# https://www.python.org/downloads/

# Verify installation
python --version
```

### Step 2: Clone and Install Argus

```powershell
# Clone repository
cd C:\Projects
git clone https://github.com/your-org/argus.git
cd argus

# Create virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install package
pip install --upgrade pip
pip install -e ".[dev]"

# Verify installation
python -m argus --version
python -m argus smoke
```

### Step 3: Configure Environment

Create `.env` file in project root:

```powershell
# Create .env file
@"
# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
TELEGRAM_PARSE_MODE=MarkdownV2

# Database (use Docker or local PostgreSQL)
DATABASE_URL=postgresql://argus:password@localhost:5432/argus

# LLM
OPENROUTER_API_KEY=sk-or-v1-your_key_here

# Logging
LOG_LEVEL=DEBUG
"@ | Out-File -Encoding UTF8 .env
```

### Step 4: PostgreSQL with Docker (Recommended)

```powershell
# Install Docker Desktop if not already installed
# https://www.docker.com/products/docker-desktop/

# Run PostgreSQL in Docker
docker run -d `
  --name argus-postgres `
  -e POSTGRES_USER=argus `
  -e POSTGRES_PASSWORD=password `
  -e POSTGRES_DB=argus `
  -p 5432:5432 `
  postgres:14

# Verify connection
docker exec -it argus-postgres psql -U argus -d argus -c "SELECT 1"
```

### Step 5: Database Setup

```powershell
# Activate venv
.\venv\Scripts\Activate.ps1

# Run migrations
python -m argus db migrate

# Create partitions
python -m argus db create-partitions --days 7
```

### Step 6: Task Scheduler Setup (Optional)

For local testing, you can use Windows Task Scheduler to simulate cron jobs.

#### Create Ingestion Task

1. **Open Task Scheduler**
   - Press `Win + R`, type `taskschd.msc`, press Enter

2. **Create New Task**
   - Click "Create Task..." in the right panel

3. **General Tab**
   - Name: `Argus - RSS Ingestion`
   - Description: `Poll RSS feeds every 10 minutes`
   - Select "Run whether user is logged on or not"
   - Check "Run with highest privileges"

4. **Triggers Tab**
   - Click "New..."
   - Begin the task: "On a schedule"
   - Settings: Daily
   - Repeat task every: 10 minutes
   - For a duration of: Indefinitely
   - Check "Enabled"
   - Click OK

5. **Actions Tab**
   - Click "New..."
   - Action: "Start a program"
   - Program/script: `C:\Projects\argus\venv\Scripts\python.exe`
   - Add arguments: `-m argus ingest`
   - Start in: `C:\Projects\argus`
   - Click OK

6. **Conditions Tab**
   - Uncheck "Start the task only if the computer is on AC power"

7. **Settings Tab**
   - Check "Allow task to be run on demand"
   - Check "Run task as soon as possible after a scheduled start is missed"
   - Click OK

8. **Enter Password**
   - Enter your Windows password when prompted

#### Create Daily US Close Task

1. **Create New Task**
   - Name: `Argus - Daily US Close`
   - Description: `Generate and publish daily market update`

2. **Triggers Tab**
   - Click "New..."
   - Begin the task: "On a schedule"
   - Settings: Weekly
   - Check: Monday, Tuesday, Wednesday, Thursday, Friday
   - Start: `06:00:00` (adjust for your timezone)
   - Click OK

3. **Actions Tab**
   - Program/script: `C:\Projects\argus\venv\Scripts\python.exe`
   - Add arguments: `-m argus run --stream us_close_basic --mode us_close`
   - Start in: `C:\Projects\argus`

#### Create Weekend Wrap Task

1. **Create New Task**
   - Name: `Argus - Weekend Wrap`

2. **Triggers Tab**
   - Begin the task: "On a schedule"
   - Settings: Weekly
   - Check: Saturday only
   - Start: `10:00:00`

3. **Actions Tab**
   - Program/script: `C:\Projects\argus\venv\Scripts\python.exe`
   - Add arguments: `-m argus run --stream us_close_basic --mode weekend_wrap`
   - Start in: `C:\Projects\argus`

#### Create Monday Preview Task

1. **Create New Task**
   - Name: `Argus - Monday Preview`

2. **Triggers Tab**
   - Begin the task: "On a schedule"
   - Settings: Weekly
   - Check: Sunday only
   - Start: `18:10:00` (in America/New_York time - adjust for local timezone!)

3. **Actions Tab**
   - Program/script: `C:\Projects\argus\venv\Scripts\python.exe`
   - Add arguments: `-m argus run --stream us_close_basic --mode monday_preview --conditional`
   - Start in: `C:\Projects\argus`

#### Verify Tasks

```powershell
# List all Argus tasks
Get-ScheduledTask | Where-Object {$_.TaskName -like "Argus*"}

# Run a task manually
Start-ScheduledTask -TaskName "Argus - RSS Ingestion"

# Check task history
Get-ScheduledTaskInfo -TaskName "Argus - RSS Ingestion"
```

---

## Database Operations

### Migrations

```bash
# Check migration status
argus db status

# Apply pending migrations
argus db migrate

# Dry-run (show what would be applied)
argus db migrate --dry-run
```

### Partitions

News items are stored in daily partitions for efficient retention management.

```bash
# Create partitions for next 14 days
argus db create-partitions --days 14

# Check existing partitions
psql -d argus -c "SELECT tablename FROM pg_tables WHERE tablename LIKE 'news_items_%' ORDER BY tablename;"
```

### Manual Queries

```bash
# Connect to database
psql $DATABASE_URL

# Check recent runs
SELECT id, stream_name, run_mode, status, created_at 
FROM runs ORDER BY created_at DESC LIMIT 10;

# Check news item counts by day
SELECT DATE(ingested_at) as day, COUNT(*) 
FROM news_items 
GROUP BY day 
ORDER BY day DESC 
LIMIT 7;

# Check fingerprint count
SELECT COUNT(*) FROM news_fingerprints;
```

---

## Retention Management

### Automatic Cleanup

The `argus db cleanup` command drops old partitions based on retention settings in `config.yaml`:

```yaml
retention:
  news_items_days: 60      # Drop news older than 60 days
  fingerprints_days: 3650  # Keep fingerprints for 10 years (dedupe)
  runs_days: 3650          # Keep run history for 10 years
```

### Manual Cleanup

```bash
# Run cleanup immediately
argus db cleanup

# Check what would be cleaned (dry-run)
# Note: Currently no dry-run for cleanup, check logs

# Manually drop a specific partition
psql -d argus -c "DROP TABLE IF EXISTS news_items_2025_01_01;"
```

### Storage Monitoring

```bash
# Check database size
psql -d argus -c "SELECT pg_size_pretty(pg_database_size('argus'));"

# Check table sizes
psql -d argus -c "
SELECT 
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables 
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
LIMIT 10;
"
```

---

## Monitoring and Logging

### Log Locations

| Log | Location (Linux) | Purpose |
|-----|------------------|---------|
| US Close | `/var/log/argus/us_close.log` | Daily run output |
| Weekend Wrap | `/var/log/argus/weekend_wrap.log` | Weekend run output |
| Monday Preview | `/var/log/argus/monday_preview.log` | Sunday preview output |
| Ingestion | `/var/log/argus/ingest.log` | RSS polling output |
| Cleanup | `/var/log/argus/cleanup.log` | Retention cleanup output |

### Health Checks

```bash
# Check last successful run
psql -d argus -c "
SELECT run_mode, status, created_at, completed_at 
FROM runs 
WHERE status = 'completed'
ORDER BY created_at DESC 
LIMIT 5;
"

# Check for failed runs
psql -d argus -c "
SELECT id, run_mode, status, error, created_at 
FROM runs 
WHERE status = 'failed'
ORDER BY created_at DESC 
LIMIT 5;
"

# Check ingestion health (items in last 24h)
psql -d argus -c "
SELECT COUNT(*) as items_24h 
FROM news_items 
WHERE ingested_at > NOW() - INTERVAL '24 hours';
"
```

### Alerts (Optional)

For production monitoring, consider:

1. **Healthchecks.io** - Ping-based monitoring for cron jobs
2. **Uptime Kuma** - Self-hosted monitoring
3. **Telegram alerts** - Send to a separate admin channel on failures

---

## Troubleshooting

### Common Issues

#### "Database connection failed"

```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Check connection string
echo $DATABASE_URL

# Test connection
psql $DATABASE_URL -c "SELECT 1"
```

#### "OPENROUTER_API_KEY not set"

```bash
# Check .env file exists and is readable
cat .env | grep OPENROUTER

# Ensure .env is being loaded
python -c "from dotenv import load_dotenv; load_dotenv(); import os; print(os.getenv('OPENROUTER_API_KEY', 'NOT SET'))"
```

#### "Telegram send failed"

```bash
# Test Telegram credentials
curl -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe"

# Check chat ID is correct
curl -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -d "chat_id=${TELEGRAM_CHAT_ID}" \
  -d "text=Test message"
```

#### "No news items found"

```bash
# Check RSS feeds are configured
cat rss/us_close_basic.txt

# Run ingestion manually
argus ingest --dry-run

# Check if items exist in DB
psql -d argus -c "SELECT COUNT(*) FROM news_items WHERE ingested_at > NOW() - INTERVAL '24 hours';"
```

#### "Validation failed"

```bash
# Run smoke test to check fixtures
argus smoke --verbose --test-invalid

# Check for hallucination patterns
argus generate --bundle-file bundle.json --dry-run
```

### Getting Help

1. Check logs for detailed error messages
2. Run with `LOG_LEVEL=DEBUG` for verbose output
3. Use `--dry-run` flags to test without side effects
4. Run `argus smoke` to verify basic functionality
