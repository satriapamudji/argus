# Task 11: Implement Telegram publisher + persistence

## Goal
Publish validated messages to Telegram and store send results for audit/replay.

## Dependencies
- Depends on Task 01
- Depends on Task 02
- Depends on Task 10

## References
- `tasks/01_plan/spec.md` ((16) Secrets & Configuration, (5) Telegram formatting)

## Scope
- Send via Telegram Bot API using `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`.
- Publish using `parse_mode=MarkdownV2` and enforce MarkdownV2 escaping rules.
- Persist message content, Telegram message id, and send status to `messages`.

## Acceptance criteria
- A dry-run mode prints the exact payload without sending.
- A real send records the Telegram message id and the final message text in DB.
