# Task 13: Smoke Fixtures + Operator Documentation

## Summary
Made the Argus system easy to run, test, and operate by adding fixture data for offline smoke testing, a CLI smoke command, and comprehensive operator documentation including cron/scheduler setup.

## What Was Before
- No fixture data for testing the generation/validation pipeline offline
- No way to run a quick smoke test without network access, database, or API keys
- README.md was minimal (44 lines) with just Quick Start
- No operator documentation for deployment, cron setup, or Windows Task Scheduler

## What Changed

### 1. Fixture Data (`tests/fixtures/`)

Created sample data files for offline testing:

| File | Purpose |
|------|---------|
| `facts_bundle.json` | Sample facts bundle with exact values from `telegram_message.example.md` |
| `generated_message_valid.md` | Valid LLM-style message that passes all validation checks |
| `generated_message_invalid.md` | Invalid message with hallucinations for testing rejection |

The facts bundle includes:
- Market snapshot: S&P 6902.05, Dow 48977.18, Nasdaq 23395.82
- Date: 6 January 2026
- 3 news items with proper metadata
- 2 calendar events (ISM Services PMI, FOMC Minutes)

The invalid fixture contains:
- Hallucinated percentage (7.5% not in bundle)
- Fake URL (reuters.com/fake-article)
- Missing Sources section
- Wrong bullet counts

### 2. Smoke Command (`src/argus/cli.py`)

Added new CLI command for offline testing:

```bash
# Basic smoke test
argus smoke

# Verbose output with validation details
argus smoke --verbose

# Also test that invalid fixtures are correctly rejected
argus smoke --test-invalid

# Use custom fixtures directory
argus smoke --fixtures-dir /path/to/fixtures
```

Features:
- No network, database, or LLM API required
- Loads fixture bundle and message
- Builds news contexts from bundle
- Runs full validation pipeline
- Reports pass/fail with details
- Windows console compatible (ASCII `[OK]`/`[FAIL]` instead of Unicode)

### 3. Expanded README.md

Expanded from ~44 lines to ~180 lines including:

| Section | Content |
|---------|---------|
| Environment Variables | Required and optional env vars table |
| Configuration | `config.yaml` structure, RSS feed setup |
| Commands Reference | All main, database, and calendar commands |
| Smoke Testing | How to run offline tests |
| Architecture | ASCII diagram of pipeline |
| Link to Operations Guide | For deployment details |

### 4. Operations Guide (`docs/OPERATIONS.md`)

Created comprehensive ~500 line deployment guide including:

**Linux VPS Deployment:**
- System preparation (Python 3.11+, PostgreSQL)
- User creation and permissions
- Installation from git
- PostgreSQL setup with extension
- Cron configuration with `CRON_TZ` for SGT/NY timezones
- All three schedule types (us_close, weekend_wrap, monday_preview)
- Retention job and log rotation

**Windows Development:**
- Python installation
- Docker for PostgreSQL
- Virtual environment setup
- Task Scheduler configuration:
  - Basic task creation
  - Trigger timing for each job type
  - Action configuration with Python paths
- Manual command examples

**Operations:**
- Database migrations
- Partition management
- Retention operations
- Monitoring and logging
- Troubleshooting common issues

## Files Created/Modified

| File | Change |
|------|--------|
| `tests/fixtures/facts_bundle.json` | **Created** - Sample facts bundle |
| `tests/fixtures/generated_message_valid.md` | **Created** - Valid message fixture |
| `tests/fixtures/generated_message_invalid.md` | **Created** - Invalid message fixture |
| `src/argus/cli.py` | **Modified** - Added ~200 lines for smoke command |
| `README.md` | **Replaced** - Expanded to ~180 lines |
| `docs/OPERATIONS.md` | **Created** - ~500 line deployment guide |

## Reasoning

From `tasks/01_plan/spec.md`:
> "A new developer can run the fixture smoke flow end-to-end without network access"
> "Docs include the exact run commands and required env vars"

The smoke command enables:
1. **CI/CD integration**: Quick validation without external dependencies
2. **Developer onboarding**: Verify setup before configuring secrets
3. **Debugging**: Isolate validation issues from network/LLM issues

The operations guide ensures:
1. **Reproducible deployment**: Step-by-step instructions
2. **Cross-platform support**: Both Linux production and Windows development
3. **Timezone handling**: Proper `CRON_TZ` for SGT-based scheduling

## Acceptance Criteria Status

| Criterion | Status |
|-----------|--------|
| Sample `facts_bundle.json` fixture | Done |
| Sample generated messages (valid/invalid) | Done |
| Repeatable smoke command runs generation+validation from fixtures | Done |
| New developer can run smoke flow without network access | Done |
| Docs include environment variables | Done |
| Docs include config layout | Done |
| Docs include cron setup for SGT + NY timezones | Done |
| Docs include retention job operation | Done |

## Test Results

- All 470 tests pass (4 skipped are expected integration tests)
- Smoke command verified working:
  - `argus smoke --verbose` - PASSED
  - `argus smoke --test-invalid` - PASSED (correctly rejects invalid fixture)
- Ruff linting: 6 issues auto-fixed
- Mypy: Pre-existing library stub warnings only (no new issues from Task 13)
