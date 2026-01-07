# Task 07: Add market snapshot + calendar data adapters

## Goal
Produce the market and catalyst inputs required by the facts bundle.

## Dependencies
- Depends on Task 01

## References
- `tasks/01_plan/spec.md` ((4) Scheduling & Timezones, (4) US Holidays & Half-days, (6) Data Requirements, (5) Output Format Contract)

## Scope
- Fetch US cash close snapshot for S&P 500, Dow, Nasdaq:
  - level, 1D % change, 1D point change (vs prior close)
- Optional cross-asset metrics (US10Y, DXY, WTI, gold/silver, VIX, breadth/sectors) when configured and reliable.
- Build a next catalysts list (next 3-7 events) with explicit timezone labeling (UTC) for `*Key Dates (UTC)*`.
- Add a US market calendar adapter (NYSE): trading days, holidays, and half-days/early closes.

## Acceptance criteria
- A single command can fetch a snapshot for a known trading date and return a normalized internal structure.
- Missing optional fields do not break facts bundle creation.
