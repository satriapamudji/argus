<div align="center">

# Argus

Automated market briefings for Telegram, built for production reliability.

Ingest curated news feeds and market data, score and select high-signal items, generate structured updates with an LLM, validate output, and publish on schedule across multiple streams.

![Python](https://img.shields.io/badge/python-3.12%2B-blue)
![Runtime](https://img.shields.io/badge/runtime-cli%20%2B%20daemon-0A7EA4)
![Database](https://img.shields.io/badge/database-postgresql-336791)
![Delivery](https://img.shields.io/badge/delivery-telegram-2CA5E0)

</div>

> [!WARNING]
> `TELEGRAM_BOT_TOKEN`, `OPENROUTER_API_KEY`, and `DATABASE_URL` are secrets.
> Keep them in `.env` only. Never commit `.env`.

## Contents

- [What Argus does](#what-argus-does)
- [Architecture](#architecture)
- [Run modes](#run-modes)
- [Quick start](#quick-start)
- [Command reference](#command-reference)
- [Configuration](#configuration)
- [Telegram control plane](#telegram-control-plane)
- [Debugging and QA](#debugging-and-qa)
- [Production operations](#production-operations)
- [Development](#development)
- [Repository layout](#repository-layout)
- [Documentation](#documentation)
- [Security notes](#security-notes)
- [License](#license)

## What Argus does

- Multi-stream execution (for example `us_markets`, `crypto`).
- End-to-end pipeline: `ingest -> score -> enrich -> bundle -> generate -> validate -> publish`.
- Pluggable providers per stage (`rss` or `api_newsapi`, multiple scoring versions, `telegram` or `null` publisher).
- DB-backed broadcast fanout for per-stream Telegram subscriptions.
- Long-running daemon scheduler with health endpoints and job history.

## Architecture

```text
Feeds/APIs -> Ingestion -> Scoring -> Enrichment -> Facts Bundle -> LLM Generate -> Validator -> Publisher
                      \___________________________________________________________/
                                      PostgreSQL persistence
```

Core runtime path:
- CLI entrypoint: `src/argus/cli.py`
- Config loading: `src/argus/config.py`
- Orchestration: `src/argus/orchestrator/orchestrator.py`
- Stage provider registry: `src/argus/pipeline/registry.py`
- Facts bundle builders:
  - `src/argus/facts_bundle/builder.py` (US markets)
  - `src/argus/facts_bundle/crypto_builder.py` (crypto)

## Run modes

| Mode | Primary use | Window | Typical daemon schedule |
|---|---|---:|---|
| `us_close` | Daily US close recap | 24h | Tue-Fri, SGT |
| `weekend_wrap` | Weekly wrap | 120h | Saturday, SGT |
| `monday_preview` | Risk-gated week-ahead preview | 120h | Sunday, New York |
| `crypto_daily` | Daily crypto recap | 24h | Daily, UTC |

`monday_preview` supports conditional publish using `risk_score` from calendar + market + headline components.

## Quick start

### 1) Local setup

Windows (PowerShell):

```powershell
copy .env.example .env
notepad .env
pip install -e ".[dev]"
argus --version
argus smoke
```

Linux/macOS:

```bash
cp .env.example .env
$EDITOR .env
pip install -e ".[dev]"
argus --version
argus smoke
```

### 2) Validate config safely

```bash
argus run --stream us_markets --mode us_close --dry-run
argus run --stream us_markets --mode us_close --skip-publish --print-message
```

### 3) Online prerequisites and first real run

```bash
argus db migrate
argus run --stream us_markets --mode us_close
```

## Command reference

### Full pipeline

```bash
argus run --stream us_markets --mode us_close
argus run --stream us_markets --mode monday_preview --conditional
argus run --stream crypto --mode crypto_daily
```

### Stage commands

```bash
argus ingest --stream us_markets
argus score --stream us_markets --window-hours 24
argus enrich --stream us_markets --window-hours 24
argus bundle --mode us_close --output bundle.json --dry-run
argus generate --bundle-file bundle.json --output message.txt
argus publish --file message.txt --dry-run
```

### Daemon commands

```bash
argus daemon start
argus daemon status
argus daemon trigger ingest:crypto
argus daemon history crypto_daily:crypto
```

### Utility commands

```bash
argus db status
argus calendar status
argus newsapi sources --categories business
argus show --run-id 15
```

## Configuration

Argus reads:
1. `.env` for secrets and deployment-specific values.
2. `config.yaml` for streams, schedules, providers, constraints, and daemon behavior.

### Required environment variables

| Variable | Purpose |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot token from `@BotFather` |
| `TELEGRAM_CHAT_ID` | Legacy fallback destination when stream subscriptions are empty |
| `DATABASE_URL` | PostgreSQL connection string |
| `OPENROUTER_API_KEY` | LLM generation key |

### Common optional environment variables

| Variable | Default | Purpose |
|---|---|---|
| `NEWS_API_KEYS` | unset | Comma-separated keys for TheNewsAPI provider |
| `TELEGRAM_OWNER_USER_ID` | unset | Control-plane owner for approvals |
| `TELEGRAM_ADMIN_CHAT_ID` | unset | Admin chat for approval workflow |
| `TELEGRAM_PARSE_MODE` | `MarkdownV2` | Telegram parse mode |
| `CHARTINSPECT_API` | unset | Optional crypto OHLCV source |
| `LOG_LEVEL` | `INFO` | Runtime logging level |

### Provider keys (`config.yaml`)

| Stage | Supported values |
|---|---|
| `providers.ingestion` | `rss`, `api_newsapi` |
| `providers.scoring` | `heuristic_v1`, `heuristic_v2`, `heuristic_v3` |
| `providers.enrichment` | `fetch_extract` |
| `providers.publisher` | `telegram`, `null` |

### Minimal multi-stream example

```yaml
streams:
  us_markets:
    enabled: true
    providers:
      ingestion: rss
      scoring: heuristic_v2
      enrichment: fetch_extract
      publisher: telegram
    rss:
      allowlist_files: ["rss/us_markets.txt"]
    schedule:
      daily_us_close_sgt: "06:00"
      weekend_wrap_sgt: "10:00"
      monday_preview_ny: "SUN 18:10"

  crypto:
    enabled: true
    providers:
      ingestion: rss
      scoring: heuristic_v3
      enrichment: fetch_extract
      publisher: telegram
    rss:
      allowlist_files: ["rss/crypto.txt"]
    schedule:
      daily_crypto_utc: "00:00"
```

RSS allowlists are one URL per line in `rss/*.txt`.

## Telegram control plane

If both `TELEGRAM_OWNER_USER_ID` and `TELEGRAM_ADMIN_CHAT_ID` are configured, daemon mode also runs Telegram onboarding/subscription control.

User flow:
1. `/start`
2. `/access`
3. After approval: `/streams`, `/subscribe <stream>`, `/unsubscribe <stream>`, `/status`

Admin flow (owner only):
1. `/requests`
2. `/approve <id>` or `/deny <id> [reason]`

Publish routing:
- If enabled stream subscriptions exist, Argus broadcasts to authorized subscribers.
- If none exist, Argus falls back to `TELEGRAM_CHAT_ID`.

## Debugging and QA

### Offline smoke test

```bash
argus smoke
argus smoke --verbose
argus smoke --test-invalid
```

### RSS preview (no DB writes)

```bash
argus rss preview --url "https://feeds.bbci.co.uk/news/rss.xml" --limit 3
argus rss preview --allowlist "rss/us_markets.txt" --json --limit 5
argus rss preview --stream crypto --limit 5
```

### DB-free trace

```bash
argus trace --stream us_markets --output trace.json
argus trace --stream crypto --mode crypto_daily --scoring v3 --output trace.json
argus trace --stream us_markets --skip-generate --output trace.json
```

Trace output includes stage timing, scored-item breakdowns, selected bundle items, and generated message (unless skipped).

### Scoring evaluation utility

```bash
argus evaluate --days 1
argus evaluate --json --topk 20
```

## Production operations

Daemon mode is the recommended production deployment:
- Internal APScheduler for ingest/report/retention jobs.
- Local health endpoints (`/ping`, `/health`, `/health/jobs/{job_id}/history`).
- Per-stream job IDs and manual triggering (`job:stream`).
- Catch-up policy support for missed jobs.

See `docs/OPERATIONS.md` for systemd setup and operational runbooks.

## Development

```bash
pip install -e ".[dev]"
pytest
pytest --cov=argus
mypy src/
ruff check src/
ruff check --fix src/
```

## Repository layout

- `src/argus/`: main package and CLI.
- `tests/`: unit/integration test suite and fixtures.
- `rss/`: feed allowlists (`*.txt`).
- `docs/`: operations, design, and integration docs.
- `scripts/`: helper scripts for local workflows.

## Documentation

- Operations: `docs/OPERATIONS.md`
- Design: `docs/design/`
- Integrations: `docs/integrations/`
- Config baseline: `config.yaml`
- Environment template: `.env.example`

## Security notes

- Never commit `.env` or API keys.
- Rotate credentials immediately after any leak.
- Keep `config.yaml` non-secret and reviewable.
- Use `--dry-run`/`--skip-publish` after config changes before live publishing.

## License

MIT
