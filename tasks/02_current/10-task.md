# Task 10: Implement validator + hallucination guard

## Goal
Automatically reject malformed or hallucinatory messages and retry once.

## Dependencies
- Depends on Task 08
- Depends on Task 09

## References
- `tasks/01_plan/spec.md` ((3) Facts Bundle is the Source of Truth, (8) Architecture: Validator, (5) Telegram formatting)

## Scope
- Validate required sections, bullet counts, and formatting (MarkdownV2-compatible).
- Hallucination guard: detect numbers/entities/links not present in facts bundle.
- Retry once with a corrective prompt; fallback to a minimal safe message if still invalid.
- Persist validation results to the `runs` record.

## Acceptance criteria
- Validator rejects known-bad fixtures (missing sections, extra numbers).
- Retry/fallback behavior is deterministic and auditable in DB.
