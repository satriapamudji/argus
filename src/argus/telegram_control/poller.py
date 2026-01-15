"""Telegram long-polling receiver integrated into daemon.

This is designed to be robust and restart-safe by persisting update offset in DB.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from argus.config import ArgusConfig, is_job_enabled_for_stream
from argus.db.connection import get_connection
from argus.db.telegram_repository import (
    approve_access_request,
    create_access_request,
    deny_access_request,
    is_chat_authorized,
    list_enabled_subscriptions,
    list_pending_access_requests,
    set_bot_state,
    set_subscription_enabled,
    upsert_chat,
    get_bot_state,
)
from argus.telegram_control.client import TelegramBotApi
from argus.telegram_control.commands import parse_command

import httpx

logger = logging.getLogger(__name__)

BOT_STATE_OFFSET_KEY = "telegram_update_offset"
# Stores a pending deny action started via inline button: {"rid": <int>}
BOT_STATE_PENDING_DENY_KEY = "telegram_pending_deny"


@dataclass(frozen=True)
class TelegramControlPlaneConfig:
    owner_user_id: int
    admin_chat_id: int


def _get_control_plane_config() -> Optional[TelegramControlPlaneConfig]:
    owner_raw = os.getenv("TELEGRAM_OWNER_USER_ID", "").strip()
    admin_raw = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "").strip()

    if not owner_raw or not admin_raw:
        return None

    try:
        return TelegramControlPlaneConfig(
            owner_user_id=int(owner_raw),
            admin_chat_id=int(admin_raw),
        )
    except ValueError:
        raise ValueError("TELEGRAM_OWNER_USER_ID and TELEGRAM_ADMIN_CHAT_ID must be integers")


def _escape_md_v2(text: str) -> str:
    # Keep it small; we only use this for bot replies.
    special = r"_[]()~`>#+-=|{}.!\\"
    out = []
    for ch in text:
        if ch in special:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def _format_handle(from_username: str | None) -> str:
    """Format a user handle for greetings.

    Telegram `username` is without '@'. If missing, we fall back to a generic greeting.
    We intentionally do not use `first_name` to keep greetings consistent across users.
    """

    if from_username:
        return f"@{from_username}"
    return "there"


def _admin_access_request_keyboard(request_id: int) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "Approve", "callback_data": f"access:approve:{request_id}"},
                {"text": "Deny", "callback_data": f"access:deny:{request_id}"},
            ]
        ]
    }


def _format_countdown(now_utc: datetime, next_run: datetime) -> tuple[int, int]:
    """Return (hours, minutes) until next_run.

    If next_run is in the past, clamps to (0, 0).
    """

    delta_seconds = int((next_run - now_utc).total_seconds())
    if delta_seconds <= 0:
        return 0, 0

    hours = delta_seconds // 3600
    minutes = (delta_seconds % 3600) // 60
    return hours, minutes


def _get_next_report_run_utc(config: ArgusConfig, stream_name: str, now_utc: datetime) -> datetime | None:
    """Best-effort next report run time for a stream (UTC).

    This mirrors the daemon scheduling model:
    - ingest is separate (interval)
    - report jobs (us_close/weekend_wrap/monday_preview/crypto_daily) publish updates
    """
    try:
        from apscheduler.triggers.cron import CronTrigger
    except Exception:
        return None

    try:
        stream_cfg = config.get_stream(stream_name)
    except Exception:
        return None

    triggers: list[CronTrigger] = []

    # US Close: Tue-Fri in Asia/Singapore
    if is_job_enabled_for_stream(stream_cfg, "us_close", config.daemon):
        hour, minute = (int(x) for x in stream_cfg.schedule.daily_us_close_sgt.split(":", 1))
        triggers.append(
            CronTrigger(
                hour=hour,
                minute=minute,
                day_of_week="tue-fri",
                timezone="Asia/Singapore",
            )
        )

    # Weekend Wrap: Saturday in Asia/Singapore
    if is_job_enabled_for_stream(stream_cfg, "weekend_wrap", config.daemon):
        hour, minute = (int(x) for x in stream_cfg.schedule.weekend_wrap_sgt.split(":", 1))
        triggers.append(
            CronTrigger(hour=hour, minute=minute, day_of_week="sat", timezone="Asia/Singapore")
        )

    # Monday Preview: Sunday in America/New_York (monday_preview_ny may include "SUN 18:10")
    if is_job_enabled_for_stream(stream_cfg, "monday_preview", config.daemon):
        parts = stream_cfg.schedule.monday_preview_ny.split()
        time_str = parts[-1] if len(parts) > 1 else parts[0]
        hour, minute = (int(x) for x in time_str.split(":", 1))
        triggers.append(
            CronTrigger(hour=hour, minute=minute, day_of_week="sun", timezone="America/New_York")
        )

    # Crypto Daily: daily in UTC
    if is_job_enabled_for_stream(stream_cfg, "crypto_daily", config.daemon):
        hour, minute = (int(x) for x in stream_cfg.schedule.daily_crypto_utc.split(":", 1))
        triggers.append(CronTrigger(hour=hour, minute=minute, timezone="UTC"))

    next_runs: list[datetime] = []
    for trigger in triggers:
        nxt = trigger.get_next_fire_time(previous_fire_time=None, now=now_utc)
        if nxt is not None:
            next_runs.append(nxt.astimezone(timezone.utc))

    return min(next_runs) if next_runs else None


def _poll_iteration(
    config: ArgusConfig,
    cp: TelegramControlPlaneConfig,
    api: TelegramBotApi,
) -> bool:
    """Run one iteration of the Telegram polling loop.

    Returns True to continue polling, False to sleep before retry.
    This is a blocking function meant to be run in an executor.
    """
    offset = None
    try:
        conn = get_connection()
        try:
            offset_raw = get_bot_state(conn, key=BOT_STATE_OFFSET_KEY)
            offset = int(offset_raw) if offset_raw is not None else None
        finally:
            conn.close()
    except Exception:
        logger.exception("Failed reading telegram offset from DB")

    updates = []
    try:
        updates = api.get_updates(offset=offset, timeout=30)
    except (httpx.ReadTimeout, httpx.ConnectTimeout):
        # Expected occasionally during long polling / transient network issues.
        logger.warning("Telegram getUpdates timed out; continuing")
        return True
    except Exception:
        logger.exception("Telegram getUpdates failed")
        return False  # Signal to sleep before retry

    max_update_id: Optional[int] = None
    for upd in updates:
        uid = upd.get("update_id")
        if isinstance(uid, int):
            max_update_id = uid if max_update_id is None else max(max_update_id, uid)

        try:
            _handle_update(config, cp, api, upd)
        except Exception:
            logger.exception("Error handling telegram update")

    if max_update_id is not None:
        try:
            conn = get_connection()
            try:
                set_bot_state(conn, key=BOT_STATE_OFFSET_KEY, value=str(max_update_id + 1))
            finally:
                conn.close()
        except Exception:
            logger.exception("Failed persisting telegram offset")

    return True


async def run_telegram_control_plane(config: ArgusConfig) -> None:
    """Run Telegram polling loop until cancelled."""

    telegram_cfg = config.stream.telegram
    bot_token = telegram_cfg.bot_token
    if not bot_token:
        logger.info("Telegram control plane disabled: TELEGRAM_BOT_TOKEN not set")
        return

    cp = _get_control_plane_config()
    if cp is None:
        logger.info(
            "Telegram control plane disabled: missing TELEGRAM_OWNER_USER_ID or TELEGRAM_ADMIN_CHAT_ID"
        )
        return

    api = TelegramBotApi(bot_token=bot_token)
    loop = asyncio.get_event_loop()

    try:
        while True:
            # Run blocking poll iteration in executor to avoid blocking event loop
            continue_immediately = await loop.run_in_executor(
                None, _poll_iteration, config, cp, api
            )
            if not continue_immediately:
                await asyncio.sleep(2)
    except asyncio.CancelledError:
        logger.info("Telegram control plane cancelled")
        raise
    finally:
        api.close()


def _handle_update(
    config: ArgusConfig, cp: TelegramControlPlaneConfig, api: TelegramBotApi, upd: dict[str, Any]
) -> None:
    # Inline button callbacks
    callback = upd.get("callback_query")
    if isinstance(callback, dict):
        _handle_callback_query(config, cp, api, callback)
        return

    message = upd.get("message") or upd.get("edited_message")
    if not isinstance(message, dict):
        return

    chat = message.get("chat")
    if not isinstance(chat, dict):
        return

    chat_id = chat.get("id")
    chat_type = chat.get("type")
    chat_title = chat.get("title")

    if not isinstance(chat_id, int) or not isinstance(chat_type, str):
        return

    from_user_raw = message.get("from")
    from_user = from_user_raw if isinstance(from_user_raw, dict) else {}
    from_user_id = from_user.get("id") if isinstance(from_user.get("id"), int) else None
    from_username = (
        from_user.get("username") if isinstance(from_user.get("username"), str) else None
    )

    text = message.get("text") if isinstance(message.get("text"), str) else None

    conn = get_connection()
    try:
        upsert_chat(conn, chat_id=chat_id, chat_type=chat_type, chat_title=chat_title)

        # Deny flow: if admin previously pressed Deny, treat next message as reason.
        if chat_id == cp.admin_chat_id and from_user_id == cp.owner_user_id and text:
            _maybe_handle_pending_deny_reason(conn, cp=cp, api=api, text=text)

        cmd = parse_command(text)
        if cmd is None:
            return

        # Admin group commands
        if chat_id == cp.admin_chat_id:
            _handle_admin_command(
                conn,
                config=config,
                cp=cp,
                api=api,
                from_user_id=from_user_id,
                cmd_name=cmd.name,
                cmd_args=cmd.args,
            )
            return

        # User/group commands
        _handle_user_command(
            conn,
            config=config,
            cp=cp,
            api=api,
            chat_id=chat_id,
            from_user_id=from_user_id,
            from_username=from_username,
            cmd_name=cmd.name,
            cmd_args=cmd.args,
        )
    finally:
        conn.close()


def _handle_callback_query(
    config: ArgusConfig,
    cp: TelegramControlPlaneConfig,
    api: TelegramBotApi,
    callback: dict[str, Any],
) -> None:
    data = callback.get("data") if isinstance(callback.get("data"), str) else None
    from_user_raw = callback.get("from")
    from_user = from_user_raw if isinstance(from_user_raw, dict) else {}
    from_user_id = from_user.get("id") if isinstance(from_user.get("id"), int) else None

    message = callback.get("message") if isinstance(callback.get("message"), dict) else None
    chat = message.get("chat") if isinstance(message, dict) else None
    chat_id = chat.get("id") if isinstance(chat, dict) else None

    if chat_id != cp.admin_chat_id:
        return
    if from_user_id != cp.owner_user_id:
        return
    if not data:
        return

    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "access":
        return

    action = parts[1]
    try:
        rid = int(parts[2])
    except ValueError:
        return

    # Button clicks are only visible in the admin chat. We persist/act via DB.
    conn = get_connection()
    try:
        if action == "approve":
            target_chat_id = approve_access_request(
                conn, request_id=rid, approved_by_user_id=cp.owner_user_id
            )
            if target_chat_id is None:
                api.send_message(
                    chat_id=cp.admin_chat_id,
                    text=_escape_md_v2(f"Request A-{rid} not found/pending."),
                )
                return
            api.send_message(chat_id=cp.admin_chat_id, text=_escape_md_v2(f"Approved A-{rid}."))
            api.send_message(
                chat_id=target_chat_id,
                text=_escape_md_v2(
                    "Your access request has been approved. What's next?\n\n"
                    "1. Run /streams to see the streams that we currently have\n"
                    "2. Subscribe to a stream by doing /subscribe <stream>"
                ),
            )
            return

        if action == "deny":
            # Start deny-with-reason flow: store pending rid, then prompt admin.
            set_bot_state(conn, key=BOT_STATE_PENDING_DENY_KEY, value=str(rid))
            api.send_message(
                chat_id=cp.admin_chat_id,
                text=_escape_md_v2(
                    f"Send the deny reason for A-{rid} as your next message."
                    "\nOr use /deny <id> [reason]"
                ),
            )
            return
    finally:
        conn.close()


def _maybe_handle_pending_deny_reason(
    conn, *, cp: TelegramControlPlaneConfig, api: TelegramBotApi, text: str
) -> None:
    pending = get_bot_state(conn, key=BOT_STATE_PENDING_DENY_KEY)
    if not pending:
        return

    try:
        rid = int(pending)
    except ValueError:
        set_bot_state(conn, key=BOT_STATE_PENDING_DENY_KEY, value="")
        return

    reason = text.strip()
    if not reason:
        api.send_message(chat_id=cp.admin_chat_id, text=_escape_md_v2("Reason cannot be empty."))
        return

    # Clear pending state first to avoid double-deny if downstream errors.
    set_bot_state(conn, key=BOT_STATE_PENDING_DENY_KEY, value="")

    target_chat_id = deny_access_request(
        conn, request_id=rid, denied_by_user_id=cp.owner_user_id, reason=reason
    )
    if target_chat_id is None:
        api.send_message(
            chat_id=cp.admin_chat_id,
            text=_escape_md_v2(f"Request A-{rid} not found/pending."),
        )
        return

    api.send_message(chat_id=cp.admin_chat_id, text=_escape_md_v2(f"Denied A-{rid}."))
    api.send_message(
        chat_id=target_chat_id,
        text=_escape_md_v2("Denied. Reason: " + reason),
    )


def _handle_user_command(
    conn,
    *,
    config: ArgusConfig,
    cp: TelegramControlPlaneConfig,
    api: TelegramBotApi,
    chat_id: int,
    from_user_id: Optional[int],
    from_username: Optional[str],
    cmd_name: str,
    cmd_args: str,
) -> None:
    if cmd_name == "start":
        handle = _format_handle(from_username)
        api.send_message(
            chat_id=chat_id,
            text=_escape_md_v2(
                "Hey " + handle + ", nice to meet you.\n\n"
                "I'm Argus, and I help you see the markets.\n\n"
                "To request access, send /access and we will onboard you shortly."
            ),
        )
        return

    if cmd_name == "access":
        req, created = create_access_request(
            conn,
            chat_id=chat_id,
            requested_by_user_id=from_user_id,
            requested_by_username=from_username,
        )

        if created:
            user_msg = "Your access request has been received. Hope to see you inside!"
        else:
            user_msg = f"Your access request is already pending (A-{req.id})."

        api.send_message(chat_id=chat_id, text=_escape_md_v2(user_msg))

        requester_handle = _format_handle(from_username)
        api.send_message(
            chat_id=cp.admin_chat_id,
            text=_escape_md_v2(
                "New access request: A-"
                + str(req.id)
                + "\n"
                + f"chat_id={chat_id}\n"
                + f"user={requester_handle}\n\n"
                + "Tap Approve or Deny below."
            ),
            reply_markup=_admin_access_request_keyboard(req.id),
        )
        return

    if cmd_name == "streams":
        if not is_chat_authorized(conn, chat_id=chat_id):
            api.send_message(
                chat_id=chat_id, text=_escape_md_v2("Not authorized. Request access with /access.")
            )
            return
        streams = config.list_streams()
        lines = ["Available streams:"] + [f"{i + 1}. {name}" for i, name in enumerate(streams)]
        api.send_message(chat_id=chat_id, text=_escape_md_v2("\n".join(lines)))
        return

    if cmd_name == "subscribe":
        if not is_chat_authorized(conn, chat_id=chat_id):
            api.send_message(
                chat_id=chat_id, text=_escape_md_v2("Not authorized. Request access with /access.")
            )
            return
        stream = cmd_args.strip()
        if not stream:
            api.send_message(chat_id=chat_id, text=_escape_md_v2("Usage: /subscribe <stream>"))
            return
        if stream not in config.list_streams():
            api.send_message(chat_id=chat_id, text=_escape_md_v2(f"Unknown stream: {stream}"))
            return
        set_subscription_enabled(
            conn, chat_id=chat_id, stream_name=stream, enabled=True, actor_user_id=from_user_id
        )
        msg = f"You are subscribed to {stream}."

        # Best-effort countdown to the stream's next report job run.
        # (This is cosmetic; the daemon remains the source of truth.)
        now = datetime.now(timezone.utc)
        next_run = _get_next_report_run_utc(config, stream_name=stream, now_utc=now)

        if next_run is not None:
            h, m = _format_countdown(now, next_run)
            msg += f" The next update will be in {h}h {m} mins"

        api.send_message(chat_id=chat_id, text=_escape_md_v2(msg))
        return

    if cmd_name == "unsubscribe":
        if not is_chat_authorized(conn, chat_id=chat_id):
            api.send_message(
                chat_id=chat_id, text=_escape_md_v2("Not authorized. Request access with /access.")
            )
            return
        stream = cmd_args.strip()
        if not stream:
            api.send_message(chat_id=chat_id, text=_escape_md_v2("Usage: /unsubscribe <stream>"))
            return
        set_subscription_enabled(
            conn, chat_id=chat_id, stream_name=stream, enabled=False, actor_user_id=from_user_id
        )
        api.send_message(chat_id=chat_id, text=_escape_md_v2(f"Unsubscribed from {stream}."))
        return

    if cmd_name == "status":
        authorized = is_chat_authorized(conn, chat_id=chat_id)
        subs = list_enabled_subscriptions(conn, chat_id=chat_id) if authorized else []
        api.send_message(
            chat_id=chat_id,
            text=_escape_md_v2(
                f"authorized={1 if authorized else 0}; subscriptions="
                + (", ".join(subs) if subs else "(none)")
            ),
        )
        return

    # Ignore unknown commands.


def _handle_admin_command(
    conn,
    *,
    config: ArgusConfig,
    cp: TelegramControlPlaneConfig,
    api: TelegramBotApi,
    from_user_id: Optional[int],
    cmd_name: str,
    cmd_args: str,
) -> None:
    if from_user_id != cp.owner_user_id:
        # Silent ignore to reduce drama.
        return

    if cmd_name == "requests":
        reqs = list_pending_access_requests(conn)
        if not reqs:
            api.send_message(
                chat_id=cp.admin_chat_id, text=_escape_md_v2("No pending access requests.")
            )
            return
        lines = [f"A-{r.id} chat_id={r.chat_id}" for r in reqs]
        api.send_message(
            chat_id=cp.admin_chat_id, text=_escape_md_v2("Pending:\n" + "\n".join(lines))
        )
        return

    if cmd_name == "approve":
        try:
            rid = int(cmd_args.strip())
        except ValueError:
            api.send_message(chat_id=cp.admin_chat_id, text=_escape_md_v2("Usage: /approve <id>"))
            return

        chat_id = approve_access_request(conn, request_id=rid, approved_by_user_id=cp.owner_user_id)
        if chat_id is None:
            api.send_message(
                chat_id=cp.admin_chat_id, text=_escape_md_v2(f"Request A-{rid} not found/pending.")
            )
            return

        api.send_message(chat_id=cp.admin_chat_id, text=_escape_md_v2(f"Approved A-{rid}."))
        api.send_message(
            chat_id=chat_id,
            text=_escape_md_v2(
                "Your access request has been approved. What's next?\n\n"
                "1. Run /streams to see the streams that we currently have\n"
                "2. Subscribe to a stream by doing /subscribe <stream>"
            ),
        )
        return

    if cmd_name == "deny":
        parts = cmd_args.split(maxsplit=1)
        if not parts:
            api.send_message(
                chat_id=cp.admin_chat_id, text=_escape_md_v2("Usage: /deny <id> [reason]")
            )
            return
        try:
            rid = int(parts[0])
        except ValueError:
            api.send_message(
                chat_id=cp.admin_chat_id, text=_escape_md_v2("Usage: /deny <id> [reason]")
            )
            return
        reason = parts[1].strip() if len(parts) > 1 else None
        chat_id = deny_access_request(
            conn, request_id=rid, denied_by_user_id=cp.owner_user_id, reason=reason
        )
        if chat_id is None:
            api.send_message(
                chat_id=cp.admin_chat_id, text=_escape_md_v2(f"Request A-{rid} not found/pending.")
            )
            return

        api.send_message(chat_id=cp.admin_chat_id, text=_escape_md_v2(f"Denied A-{rid}."))
        api.send_message(
            chat_id=chat_id,
            text=_escape_md_v2("Denied." + (f" Reason: {reason}" if reason else "")),
        )
        return

    # Unknown admin command ignored.
