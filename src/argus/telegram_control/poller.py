"""Telegram long-polling receiver integrated into daemon.

This is designed to be robust and restart-safe by persisting update offset in DB.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

from argus.config import ArgusConfig
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

logger = logging.getLogger(__name__)

BOT_STATE_OFFSET_KEY = "telegram_update_offset"


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

    try:
        while True:
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
            except Exception:
                logger.exception("Telegram getUpdates failed")
                await asyncio.sleep(2)
                continue

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

    except asyncio.CancelledError:
        logger.info("Telegram control plane cancelled")
        raise
    finally:
        api.close()


def _handle_update(
    config: ArgusConfig, cp: TelegramControlPlaneConfig, api: TelegramBotApi, upd: dict[str, Any]
) -> None:
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
    cmd = parse_command(text)
    if cmd is None:
        return

    conn = get_connection()
    try:
        upsert_chat(conn, chat_id=chat_id, chat_type=chat_type, chat_title=chat_title)

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
        api.send_message(
            chat_id=chat_id,
            text=_escape_md_v2(
                "Welcome to Argus. To request access, send /access. After approval, use /streams then /subscribe <stream>."
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
        api.send_message(
            chat_id=chat_id,
            text=_escape_md_v2(
                f"Access request received (A-{req.id}). Pending approval."
                if created
                else f"Access request already pending (A-{req.id})."
            ),
        )
        api.send_message(
            chat_id=cp.admin_chat_id,
            text=_escape_md_v2(
                f"New access request A-{req.id} from chat_id={chat_id}. Approve with /approve {req.id} or deny with /deny {req.id} [reason]."
            ),
        )
        return

    if cmd_name == "streams":
        if not is_chat_authorized(conn, chat_id=chat_id):
            api.send_message(
                chat_id=chat_id, text=_escape_md_v2("Not authorized. Request access with /access.")
            )
            return
        streams = config.list_streams()
        api.send_message(
            chat_id=chat_id, text=_escape_md_v2("Available streams: " + ", ".join(streams))
        )
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
        api.send_message(chat_id=chat_id, text=_escape_md_v2(f"Subscribed to {stream}."))
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
            text=_escape_md_v2("Approved. Run /streams then /subscribe <stream>."),
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
