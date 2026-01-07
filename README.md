# Argus - US Close Market Update Bot

Telegram bot that ingests news + prices, scores and curates items, generates a WhatsApp/Telegram-style "Market Update" after US close, and publishes on a schedule (SGT + NY DST-safe).

## Quick Start

```bash
# Install in development mode
pip install -e .

# Verify installation
argus --version

# Run smoke test (no network required)
argus smoke

# Run a dry-run to test configuration
argus run --stream us_close_basic --mode us_close --dry-run
```

## Environment Variables

Create a `.env` file in the project root (see `.env.example`):

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from [@BotFather](https://t.me/BotFather) | `123456789:ABCdef...` |
| `TELEGRAM_CHAT_ID` | Target chat/channel ID | `-1001234567890` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@localhost:5432/argus` |
| `OPENROUTER_API_KEY` | API key for LLM generation via [OpenRouter](https://openrouter.ai) | `sk-or-v1-...` |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_PARSE_MODE` | `MarkdownV2` | Telegram message formatting mode |
| `LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

## Configuration

Configuration is loaded from two sources:

1. **`.env`** - Secrets and deployment-specific values (never commit to git)
2. **`config.yaml`** - Non-secret stream settings, schedules, and constraints

### config.yaml Structure

```yaml
stream:
  name: us_close_basic
  enabled: true

schedule:
  daily_us_close_sgt: "06:00"    # Mon-Fri 06:00 SGT
  weekend_wrap_sgt: "10:00"      # Sat 10:00 SGT
  monday_preview_ny: "SUN 18:10" # Sun 18:10 America/New_York

retention:
  news_items_days: 60     # Keep news for 60 days
  fingerprints_days: 3650 # Keep dedupe fingerprints for 10 years
  runs_days: 3650         # Keep run history for 10 years

constraints:
  max_words_daily: 420
  max_words_weekend: 520
  max_words_preview: 320

rss:
  allowlist_files:
    - "rss/us_close_basic.txt"
  poll_interval_minutes: 10
```

### RSS Feed Configuration

RSS feeds are configured in text files under the `rss/` directory:

```
rss/
  us_close_basic.txt   # One URL per line, # for comments
```

## Commands Reference

### Main Commands

| Command | Description |
|---------|-------------|
| `argus run` | Execute a full pipeline run (ingest → score → generate → publish) |
| `argus smoke` | Run offline smoke test using fixtures (no network required) |
| `argus ingest` | Poll RSS feeds and ingest new items |
| `argus score` | Score unscored news items |
| `argus enrich` | Fetch full content for top-scored items |
| `argus bundle` | Build a facts bundle for generation |
| `argus generate` | Generate a message from a facts bundle |
| `argus publish` | Publish a message to Telegram |

### Database Commands

| Command | Description |
|---------|-------------|
| `argus db migrate` | Apply pending database migrations |
| `argus db status` | Show migration status |
| `argus db cleanup` | Run retention cleanup (drop old partitions) |
| `argus db create-partitions` | Create partitions for upcoming days |

### Calendar Commands

| Command | Description |
|---------|-------------|
| `argus calendar refresh` | Fetch latest economic calendar data |
| `argus calendar show` | Display upcoming economic events |
| `argus calendar status` | Show calendar configuration and data status |

### Daemon Commands

| Command | Description |
|---------|-------------|
| `argus daemon start` | Run daemon scheduler in foreground |
| `argus daemon status` | Show daemon and job status |
| `argus daemon trigger <job>` | Manually trigger a scheduled job |
| `argus daemon history <job>` | Show recent run history for a job |

### Common Options

```bash
# Dry run (show what would happen without executing)
argus run --mode us_close --dry-run

# Skip publishing (generate but don't send)
argus run --mode us_close --skip-publish

# Verbose output
argus smoke --verbose

# Custom config path
argus --config /path/to/config.yaml run --mode us_close
```

## Smoke Testing

Run the offline smoke test to verify the generation and validation pipeline:

```bash
# Basic smoke test
argus smoke

# Verbose output showing validation details
argus smoke --verbose

# Also test that invalid messages are correctly rejected
argus smoke --test-invalid
```

The smoke test:
1. Loads a sample facts bundle from `tests/fixtures/`
2. Loads a pre-generated message (simulating LLM output)
3. Runs the validator to ensure formatting and data integrity
4. Reports success/failure with details

**No network access, database, or API keys required.**

## Daemon Mode

For VPS deployment, Argus can run as a long-lived daemon with internal scheduling, eliminating the need for external cron configuration.

```bash
# Start daemon (foreground)
argus daemon start

# Check status
argus daemon status

# Manually trigger a job
argus daemon trigger ingest

# View job history
argus daemon history us_close
```

Configure daemon behavior in `config.yaml`:

```yaml
daemon:
  health_port: 8080
  health_bind: "127.0.0.1"
  
  jobs_enabled:
    ingest: true
    us_close: true
    weekend_wrap: true
    monday_preview: true
    retention: true
  
  # 'run_immediately' or 'skip' for missed jobs
  missed_policy:
    ingest: run_immediately
    us_close: skip
```

For systemd deployment, see the [Operations Guide](docs/OPERATIONS.md#daemon-mode-deployment-recommended).

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=argus

# Run type checking
mypy src/

# Run linting
ruff check src/

# Run linting with auto-fix
ruff check --fix src/
```

## Deployment

For detailed deployment instructions including:
- Linux VPS setup with cron
- Windows development with Task Scheduler
- Database configuration
- Retention operations

See the [Operations Guide](docs/OPERATIONS.md).

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Argus Pipeline                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────┐   ┌─────────┐   ┌──────────┐   ┌───────────────┐ │
│  │ Ingest   │ → │ Score   │ → │ Enrich   │ → │ Bundle Build  │ │
│  │ (RSS)    │   │ (Rules) │   │ (Fetch)  │   │ (Selection)   │ │
│  └──────────┘   └─────────┘   └──────────┘   └───────────────┘ │
│                                                      ↓          │
│  ┌──────────┐   ┌─────────┐   ┌──────────┐   ┌───────────────┐ │
│  │ Publish  │ ← │Validate │ ← │ Generate │ ← │ Facts Bundle  │ │
│  │(Telegram)│   │(Guards) │   │ (LLM)    │   │ (JSON)        │ │
│  └──────────┘   └─────────┘   └──────────┘   └───────────────┘ │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## License

MIT
