# Repository Guidelines

## Project Structure & Module Organization

- `src/argus/`: primary Python package (CLI entrypoint: `src/argus/cli.py`).
- `tests/`: `pytest` suite (fixtures in `tests/fixtures/`; domain-focused tests in subfolders like `tests/orchestrator/`).
- `rss/`: RSS allowlists (e.g., `rss/us_markets.txt`, one URL per line).
- `docs/`: operational and design docs (start with `docs/OPERATIONS.md`).
- `scripts/`: developer utilities for local checks and message rendering.
- `config.yaml`: non-secret stream configuration; secrets live in `.env` (see `.env.example`).

## Build, Test, and Development Commands

- `pip install -e .`: install Argus in editable mode.
- `pip install -e ".[dev]"`: install dev tools (`pytest`, `ruff`, `mypy`).
- `argus smoke`: offline smoke test (no network required).
- `argus run --stream us_markets --mode us_close --dry-run`: validates config and runs without publishing.
- `pytest`: run the full unit/integration test suite.
- `pytest --cov=argus`: run tests with coverage reporting.
- `mypy src/`: type-check the codebase (non-strict configuration).
- `ruff check src/` / `ruff check --fix src/`: lint (and auto-fix safe issues).

## Coding Style & Naming Conventions

- Python `>=3.12`, 4-space indentation, and type hints for new/modified code.
- `ruff` line length is 100 (see `pyproject.toml`); keep imports clean and avoid unused symbols.
- Naming: `snake_case` for functions/modules, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants.
- Prefer keeping I/O behind adapters (e.g., `src/argus/adapters/`) and business logic in pipeline modules.

## Testing Guidelines

- Name tests `tests/test_*.py` (or `tests/<area>/test_*.py`).
- Use `@pytest.mark.asyncio` for async behavior.
- Tests that require external services should be explicitly `skip`/`xfail` (existing pattern).
- DB-dependent tests are marked `pytest.mark.db` and should skip unless a real `DATABASE_URL` is configured.

## Commit & Pull Request Guidelines

- Follow the repo’s Conventional Commit style seen in history: `feat: …`, `fix(scope): …`, `docs: …`, `chore: …`.
- PRs should include: what changed, how to validate (`argus smoke`, `pytest`), and any config changes (`config.yaml`, `rss/*.txt`).

## Security & Configuration Tips

- Never commit `.env` or credentials; add new variables to `.env.example`.
- Treat `config.yaml` as non-secret and keep stream/provider changes reviewable and small.

