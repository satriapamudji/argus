# Task 08: Define facts bundle schema + builder

## Goal
Create a deterministic facts bundle generator; the facts bundle is the only allowed source for the generator LLM.

## Dependencies
- Depends on Task 02
- Depends on Task 04
- Depends on Task 06
- Depends on Task 07

## References
- `tasks/01_plan/spec.md` ((3) Facts Bundle is the Source of Truth, (6) Data Requirements, (5) Output Format Contract)

## Scope
- Define a concrete `facts_bundle.json` schema (and optionally JSON Schema for validation).
- Deterministically select 2-6 news items using:
  - score ranking
  - dedupe flags
  - diversity constraints (topics/sources)
- Include required market snapshot + calendar + optional cross-asset fields when available.
- Include citations metadata needed for `*Sources*` and events formatted for `*Key Dates (UTC)*`.
- Persist facts bundle JSON to `runs`.

## Acceptance criteria
- Facts bundle generation is deterministic given the same inputs/config.
- Facts bundle validates against its schema and includes everything needed to generate the message without guessing.
