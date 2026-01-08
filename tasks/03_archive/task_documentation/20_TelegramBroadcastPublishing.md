# Task 20 — Telegram Broadcast Publishing (Per-Stream Subscriptions)

## Outcome
Publishing now broadcasts a generated message to **all authorized chats subscribed to the active stream**, instead of a single global `TELEGRAM_CHAT_ID`.

Key behaviors:
- Recipient selection is per-stream (`stream_name`).
- Only recipients that are **enabled**, **authorized**, and **not blocked** receive messages.
- Best-effort fanout: failures for one chat do not abort the remaining sends.
- Legacy fallback preserved: if the stream has **no subscriptions**, publish via the existing single-destination flow (uses `TELEGRAM_CHAT_ID`).

## Implementation Details

### 1) Recipient query helper
Added a repository helper to list broadcast recipients:
- File: `src/argus/db/telegram_repository.py`
- Function: `list_broadcast_chat_ids(conn, *, stream_name: str) -> list[int]`
- Query logic:
  - `telegram_stream_subscriptions.enabled = true`
  - `telegram_chats.authorized = true`
  - `telegram_chats.blocked = false`
  - deterministic ordering by `chat_id`

### 2) Publisher integration (provider-layer fanout)
Broadcast is implemented at the **publisher provider** layer:
- File: `src/argus/pipeline/providers/publisher_telegram.py`
- Behavior:
  1. Fetch message via `get_message_by_id`.
  2. Use `list_broadcast_chat_ids(..., stream_name=config.stream.name)`.
  3. If recipients exist, loop over them and publish with explicit `chat_id`.
  4. If no recipients exist, call existing `run_publish(...)` (legacy behavior).

### 3) Message status semantics
The messages table has only one `telegram_message_id`, so broadcast aggregates results:
- If **any** destination succeeds: update message to `publish_status='published'` and store the **first successful** `telegram_message_id` + `published_at`.
- If **all** destinations fail: update message to `publish_status='failed'`.
- Dry run does not update DB.

### 4) Tests
- Added: `tests/test_telegram_broadcast_publishing.py`
  - verifies broadcast sends to all recipients
  - verifies best-effort behavior on partial failure
  - verifies dry-run skips DB updates

## Verification
- `pytest -q`:
  - `508 passed, 5 skipped`

## Notes / Future Enhancements
If we ever need per-destination auditing (message_id x chat_id), we can introduce a publish-attempts table, but it wasn’t required for this MVP.
