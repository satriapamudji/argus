# Task 20: Telegram Broadcast Publishing (Per-Stream Subscriptions)

## Goal
Change publishing from a single `TELEGRAM_CHAT_ID` target to **broadcast** to all authorized chats subscribed to the stream.

This task delivers the **data plane**:
- For each run, publish the generated message to all chat IDs subscribed to that stream.

**Depends on Task 19** for subscription storage and authorization.

## Desired Behavior
- When Argus runs `--stream us_close_basic`, publishing sends the message to:
  - all `telegram_chats` where `authorized=true` (and not blocked)
  - joined with `telegram_stream_subscriptions` where `stream_name='us_close_basic'` and `enabled=true`
- Publishing should be best-effort:
  - one failing chat should not prevent attempts to publish to other chats
  - errors should be logged per chat

## Implementation Plan

### 1) Repository query
- Add a DB query helper to list subscribed chat IDs for a given stream:
  - `enabled=true`
  - `authorized=true`
  - (optional) `blocked=false`

### 2) Publisher integration
- Replace single `TELEGRAM_CHAT_ID` publishing with a loop over subscribed chats.
- Preserve current behavior as a fallback (optional but recommended):
  - if no subscriptions exist for the stream, publish to `TELEGRAM_CHAT_ID` (if set)

### 3) Result tracking (optional)
- Optionally store per-chat publish attempts in a new table (not required for MVP):
  - message_id, chat_id, status, error, published_at

## Acceptance Criteria
- Scheduled publishing sends to all subscribed destinations per stream.
- A failure sending to one destination does not abort publishing to the remaining destinations.
