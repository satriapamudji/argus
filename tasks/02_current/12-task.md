# Task 12: Build run orchestrator + scheduling hooks

## Goal
Implement end-to-end runs (`us_close`, `weekend_wrap`, `monday_preview`) with DST-safe scheduling assumptions.

## Dependencies
- Depends on Task 01
- Depends on Task 02
- Depends on Task 03
- Depends on Task 05
- Depends on Task 06
- Depends on Task 07
- Depends on Task 08
- Depends on Task 09
- Depends on Task 10
- Depends on Task 11

## References
- `tasks/01_plan/spec.md` ((4) Scheduling & Timezones, (4) risk_score definition, (4) US Holidays & Half-days, (8) Architecture: Run Orchestrator)

## Scope
- `bin/argus run --stream us_close_basic --mode <mode>` performs:
  1) window selection
  2) shortlist + enrichment (optional)
  3) scoring + selection
  4) facts bundle creation
  5) generation + validation
  6) publish (optional)
- Implement `--conditional true` for `monday_preview` using `risk_score >= threshold`.
- Respect holiday/half-day behaviors from `tasks/01_plan/spec.md` (NYSE calendar + configured behavior).

## Acceptance criteria
- Each run mode completes with a persisted `run` artifact even if publishing is disabled.
- Cron examples in `tasks/01_plan/spec.md` map cleanly to CLI invocations.
