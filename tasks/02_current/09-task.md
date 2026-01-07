# Task 09: Implement generator LLM prompt + message renderer

## Goal
Generate the final Telegram-ready message strictly from the facts bundle.

## Dependencies
- Depends on Task 08

## References
- `tasks/01_plan/spec.md` ((5) Output Format Contract: Telegram formatting + canonical section order)
- `tasks/01_plan/telegram_message.example.md`

## Scope
- Build prompts/templates for each mode:
  - `us_close` (daily)
  - `weekend_wrap`
  - `monday_preview` (conditional)
- Enforce the output contract from `tasks/01_plan/spec.md` (including `*Key Dates (UTC)*` and `*Sources*`).
- Ensure output is MarkdownV2-compatible (section markers, bullets, links/citations).
- Respect per-mode word/bullet limits from config.

## Acceptance criteria
- Given a fixture facts bundle, generation produces a correctly formatted message.
- The generator never introduces numbers/entities not present in the facts bundle.
