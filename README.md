# Argus - Market Update Bot

Telegram bot that ingests news + prices, scores and curates items, generates WhatsApp/Telegram-style market updates across multiple run modes (e.g. `us_close`, `weekend_wrap`, `monday_preview`) within a stream (e.g. `us_markets`), and publishes on a schedule (SGT + NY DST-safe).

## Quick Start

```bash
# Install in development mode
pip install -e .

# Verify installation
argus --version

# Run smoke test (no network required)
argus smoke

# Run a dry-run to test configuration
argus run --stream us_markets --mode us_close --dry-run
```

## Environment Variables

Create a `.env` file in the project root (see `.env.example`):

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from [@BotFather](https://t.me/BotFather) | `123456789:ABCdef...` |
| `TELEGRAM_CHAT_ID` | Target chat/channel ID (legacy single-destination publishing) | `-1001234567890` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@localhost:5432/argus` |
| `OPENROUTER_API_KEY` | API key for LLM generation via [OpenRouter](https://openrouter.ai) | `sk-or-v1-...` |

### Telegram Control Plane (Access + Subscriptions)

These settings enable chat onboarding and per-stream subscriptions. The control plane runs automatically inside `argus daemon start` when these variables are set.

| Variable | Description | Example |
|----------|-------------|---------|
| `TELEGRAM_OWNER_USER_ID` | Owner Telegram user ID (only this user can approve/deny access) | `123456789` |
| `TELEGRAM_ADMIN_CHAT_ID` | Admin group chat ID where approvals happen | `-1001234567890` |

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
streams:
  us_markets:
    enabled: true
    rss:
      allowlist_files: ["rss/us_markets.txt"]
      poll_interval_minutes: 20
    schedule:
      daily_us_close_sgt: "06:00"
      weekend_wrap_sgt: "10:00"
      monday_preview_ny: "SUN 18:10"

  crypto:
    enabled: true
    rss:
      allowlist_files: ["rss/crypto.txt"]
      poll_interval_minutes: 20
    schedule:
      daily_crypto_utc: "00:00"
```

### RSS Feed Configuration

RSS feeds are configured in text files under the `rss/` directory:

```
rss/
  us_markets.txt   # One URL per line, # for comments
```

## Telegram Control Plane (Onboarding + Subscriptions)

Argus supports DB-backed per-stream subscriptions for Telegram publishing.

### Onboarding flow

In any chat with the bot:

1. `/start` — shows onboarding help
2. `/access` — request access (creates a pending request)
3. In the admin group (must be sent by `TELEGRAM_OWNER_USER_ID`):
   - `/approve <id>` or `/deny <id> [reason]`
4. After approval:
   - `/streams` — list available stream names
   - `/subscribe <stream>` — receive broadcasts for that stream
   - `/unsubscribe <stream>` — stop receiving broadcasts
   - `/status` — show authorization + current subscriptions

Admin group commands (owner only):
- `/requests` — list pending access requests

### Broadcast publishing behavior

When Argus publishes a message for a given stream, it sends it to **all authorized, enabled subscribers** for that stream.

If there are **no subscriptions** in the database for that stream, Argus falls back to the legacy single destination `TELEGRAM_CHAT_ID`.

This means being the owner/admin does **not** automatically subscribe you to broadcasts — subscribe the specific chat (DM/group/channel) you want to receive posts.

## Commands Reference

### Main Commands

| Command | Description |
|---------|-------------|
| `argus run` | Execute a full pipeline run (ingest → score → generate → publish) |
| `argus smoke` | Run offline smoke test using fixtures (no network required) |
| `argus ingest --stream <stream>` | Poll RSS feeds and ingest new items for a stream |
| `argus score --stream <stream>` | Score unscored news items for a stream |
| `argus enrich --stream <stream>` | Fetch full content for top-scored items for a stream |
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
| `argus daemon trigger <job_id_or_key>` | Manually trigger a job (supports `job:stream`) |
| `argus daemon history <job_id_or_key>` | Show recent run history (supports `job:stream`) |

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

### Scheduling model (multi-stream)

- `ingest:<stream>` runs on a short interval and continuously writes new items into the DB for that stream.
- Scheduled report jobs (`us_close:<stream>`, `crypto_daily:<stream>`, etc.) run `score → enrich → bundle → generate → publish` using the DB window (they do not ingest).

**Note:** `argus daemon start` also starts the Telegram control plane (long polling) when `TELEGRAM_OWNER_USER_ID` and `TELEGRAM_ADMIN_CHAT_ID` are set.

```bash
# Start daemon (foreground)
argus daemon start

# Check status
argus daemon status

# Manually trigger a per-stream job
argus daemon trigger ingest:crypto
argus daemon trigger crypto_daily:crypto

# View job history
argus daemon history crypto_daily:crypto
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

## Crypto Stream

- RSS allowlist: `rss/crypto.txt`
- Run locally (no publish): `argus run --stream crypto --mode crypto_daily --skip-publish --print-message`
- Optional: set `CHARTINSPECT_API` for ChartInspect OHLCV; otherwise Argus falls back to CoinGecko where possible.

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
