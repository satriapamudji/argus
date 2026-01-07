# Task 13: Add smoke fixtures + operator documentation

## Goal
Make the system easy to run, test, and operate.

## Dependencies
- Depends on Task 01
- Depends on Task 08
- Depends on Task 10
- Depends on Task 11
- Depends on Task 12

## References
- `tasks/01_plan/spec.md` ((4) Scheduling & Timezones, (5) Output Format Contract, (16) Secrets & Configuration)
- `tasks/01_plan/telegram_message.example.md`

## Scope
- Add fixture data for:
  - sample `facts_bundle.json`
  - sample generated messages (valid/invalid)
- Add a repeatable smoke command that runs generation+validation from fixtures.
- Document setup and operation (README):
  - environment variables
  - config layout
  - cron setup for SGT + NY timezones
  - retention job operation

## Acceptance criteria
- A new developer can run the fixture smoke flow end-to-end without network access (LLM calls mocked or disabled).
- Docs include the exact run commands and required env vars.
