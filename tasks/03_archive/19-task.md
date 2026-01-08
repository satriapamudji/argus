# Task 19: Telegram Access Requests + Stream Subscriptions (Control Plane)

## Goal
Enable interactive access onboarding and per-stream subscriptions via Telegram bot commands **without editing `.env`** for each new destination.

This task delivers the **control plane**:
- Owner-approved access requests (`/access`)
- Authorized chats can self-manage subscriptions (`/subscribe`, `/unsubscribe`)
- A polling-based command receiver integrated into the daemon

**Out of scope (Task 20):** changing publishing to broadcast to all subscribed chats.

## Desired Behavior

### DM flow
1) User DMs bot: `/start`
   - Bot sends welcome + instructions.
   - Bot instructs the user to request access via `/access`.
2) User sends: `/access`
   - Bot replies: "Access request received. Pending approval."
   - Bot notifies admin group with request ID.
3) Owner approves in admin group:
   - Bot notifies user: "Approved. Run `/streams` to see available streams, then subscribe with `/subscribe <stream>`."
4) User sends: `/streams`
   - Bot lists available streams.
5) User sends: `/subscribe us_close_basic` (or another listed stream)
   - Bot replies: "Subscribed to us_close_basic. You will receive updates here."

### Group flow
1) Bot is added to group.
2) Someone sends: `/access`
   - Bot replies in group: "Access request received. Pending approval."
   - Bot notifies admin group with request details.
3) Owner approves/denies; bot replies in group with outcome.
4) Authorized group can run `/streams`, then `/subscribe <stream>`.

### Rules
- `/access` is required for access request (no implicit authorization).
- `/streams` and stream subscription commands only work after the chat is authorized.
- No auto-subscribe to streams after access approval (user/group must explicitly choose a stream).
- Owner-only approve/deny in admin group.
- Once a chat is authorized, `/subscribe` and `/unsubscribe` are **immediate** (no approvals).

## Implementation Plan

### 1) Telegram update receiver (polling)
- Add a long-polling loop (`getUpdates`) inside the existing daemon (preferred) or as `argus bot start`.
- Ensure only one poller instance runs (avoid duplicate consumers).

### 2) Configuration (one-time env)
- `TELEGRAM_OWNER_USER_ID` (owner telegram user id)
- `TELEGRAM_ADMIN_CHAT_ID` (admin group chat id)
- Keep `TELEGRAM_BOT_TOKEN` as-is.

### 3) Database schema
Add tables:

#### `telegram_chats`
- chat_id (PK)
- chat_type, chat_title
- authorized (bool)
- authorized_at, authorized_by_user_id
- created_at
- blocked (optional)

#### `telegram_chat_requests`
- id (e.g. A-123)
- chat_id
- requested_by_user_id, requested_by_username
- status (pending/approved/denied)
- deny_reason
- created_at, resolved_at, resolved_by_user_id

#### `telegram_stream_subscriptions`
- chat_id
- stream_name
- enabled (bool)
- enabled_at, enabled_by_user_id
- disabled_at (optional)

### 4) Command handling
User/group:
- `/start` -> welcome text
- `/access` -> create access request + notify admin group
- `/streams` -> list streams (only if authorized)
- `/subscribe <stream>` -> subscribe immediately (only if authorized)
- `/unsubscribe <stream>` -> unsubscribe immediately (only if authorized)
- `/status` -> show authorized/subscribed status

Admin group (owner-only):
- `/requests` -> list pending access requests
- `/approve <A-123>`
- `/deny <A-123> [reason]`

## Edge Cases / Guardrails
- Telegram bots can’t message users unless user has initiated `/start`; DM access requires that.
- Handle duplicate requests: already authorized/subscribed or already pending should return friendly message.
- Group privacy mode may require bot privacy disabled or `/command@botusername`.

## Acceptance Criteria
- No need to edit `.env` to add new subscriber destinations.
- Owner can approve/deny from admin group only.
- Approved chat can discover streams via `/streams`.
- Users/groups can subscribe to specific streams after authorization.
