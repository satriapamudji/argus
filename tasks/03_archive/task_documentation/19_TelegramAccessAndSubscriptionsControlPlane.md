# Task 19: Telegram Access Requests + Stream Subscriptions (Control Plane)

## Summary
Implemented a Telegram “control plane” so Argus can onboard new DMs/groups via bot commands **without editing `.env` per destination**. Chats request access with `/access`; the owner approves/denies in a dedicated admin group. Once authorized, chats can self-manage stream subscriptions with `/subscribe` / `/unsubscribe`.

This task does **not** change the publishing data plane to broadcast to all subscribed chats (that is Task 20).

## What Changed

### 1) Database schema: Telegram control-plane tables
Added migration: `src/argus/db/migrations/002_telegram_control_plane.sql`

Creates:
- `telegram_chats`: known chats, authorization + blocked flags
- `telegram_chat_requests`: pending/approved/denied access requests (one pending per chat enforced)
- `telegram_stream_subscriptions`: per-chat per-stream enabled flag
- `telegram_bot_state`: persistence for polling offset (`telegram_update_offset`)

### 2) Repository layer for Telegram control-plane
Added: `src/argus/db/telegram_repository.py`

Key helpers:
- `upsert_chat(...)`
- `create_access_request(...)` (idempotent if already pending)
- `list_pending_access_requests(...)`
- `approve_access_request(...)` (also marks chat authorized)
- `deny_access_request(...)`
- `set_subscription_enabled(...)`
- `list_enabled_subscriptions(...)`
- `get_bot_state(...)` / `set_bot_state(...)`

### 3) Telegram polling + command router
Added module: `src/argus/telegram_control/`
- `client.py`: minimal Bot API client for `getUpdates` and `sendMessage`
- `commands.py`: command parsing (supports `/cmd@BotUsername`)
- `poller.py`: long-polling receiver + routing

Supported commands:

User/group:
- `/start` → onboarding text
- `/access` → creates access request; notifies admin group with request id `A-<id>`
- `/streams` → lists available streams (authorized only)
- `/subscribe <stream>` → immediate subscribe (authorized only)
- `/unsubscribe <stream>` → immediate unsubscribe (authorized only)
- `/status` → authorized/subscriptions summary

Admin group (owner-only):
- `/requests` → list pending access requests
- `/approve <id>` → approve access request and notify requester
- `/deny <id> [reason]` → deny request and notify requester

Guardrails:
- Only the owner (env `TELEGRAM_OWNER_USER_ID`) can approve/deny.
- Admin commands must be sent inside admin group (env `TELEGRAM_ADMIN_CHAT_ID`).
- Poll offset is persisted in DB to avoid reprocessing updates on restart.

### 4) Daemon integration
Updated: `src/argus/daemon/scheduler.py`
- Starts the Telegram control plane as a background asyncio task when daemon starts.
- Cancels the task during daemon shutdown.

### 5) Minimal environment docs updates
Updated:
- `README.md` to document `TELEGRAM_OWNER_USER_ID` and `TELEGRAM_ADMIN_CHAT_ID`
- `.env.example` to include the new vars

## Files Created/Modified

Created:
- `src/argus/db/migrations/002_telegram_control_plane.sql`
- `src/argus/db/telegram_repository.py`
- `src/argus/telegram_control/__init__.py`
- `src/argus/telegram_control/client.py`
- `src/argus/telegram_control/commands.py`
- `src/argus/telegram_control/poller.py`
- `tests/test_telegram_control_plane.py`
- `tasks/03_archive/task_documentation/19_TelegramAccessAndSubscriptionsControlPlane.md`

Modified:
- `src/argus/daemon/scheduler.py`
- `tests/test_db_migrations.py`
- `README.md`
- `.env.example`

Archived:
- `tasks/03_archive/19-task.md`

## Acceptance Criteria Status
- No need to edit `.env` to add new subscriber destinations: **Done** (via access request + DB tables)
- Owner can approve/deny from admin group only: **Done**
- Approved chat can discover streams via `/streams`: **Done**
- Users/groups can subscribe to specific streams after authorization: **Done**

## Test Results
- `pytest -q` → 506 passed, 5 skipped (existing warning about unknown pytest mark `db`)

## Notes / Follow-ups
- Task 20 will update the publishing data plane to broadcast to all subscribed chats per stream.
- Poller currently uses a minimal MarkdownV2 escaper for bot replies; published market updates remain handled by the existing Telegram publisher.
