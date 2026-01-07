# Task 01: Scaffold Python project + configuration

## Goal
Create the initial Python codebase, CLI entrypoint, and config loading needed to run Athena on a VM.

## Dependencies
- None

## References
- `tasks/01_plan/spec.md` ((2) Goals & Non-goals: Implementation defaults (v0), (4) Scheduling & Timezones, (16) Secrets & Configuration)
- `rss/us_close_basic.txt`

## Scope
- Create a Python project skeleton and a `bin/athena` CLI with `run --stream ... --mode ...`.
- Load configuration from `.env` and `config.yaml` (stream settings, schedules, retention, dedupe, enrichment, telegram).
- Add `.env.example` and `.gitignore` (exclude `.env` and local runtime artifacts).

## Acceptance criteria
- `bin/athena --help` works.
- `bin/athena run --stream us_close_basic --mode us_close --dry-run` loads config and prints resolved settings.
