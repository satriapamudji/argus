# Argus - US Close Market Update Bot

Telegram bot that ingests news + prices, scores and curates items, generates a WhatsApp/Telegram-style "Market Update" after US close, and publishes on a schedule (SGT + NY DST-safe).

## Installation

```bash
pip install -e .
```

## Usage

```bash
# Show help
bin/argus --help

# Run a dry-run to test configuration
bin/argus run --stream us_close_basic --mode us_close --dry-run
```

## Configuration

Configuration is loaded from:
1. `.env` - for secrets (Telegram tokens, database URL)
2. `config.yaml` - for non-secret settings

See `.env.example` for required environment variables.

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run type checking
mypy src/

# Run linting
ruff check src/
```
