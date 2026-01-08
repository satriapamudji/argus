"""Telegram control-plane repository helpers.

This module deliberately isolates Telegram-specific persistence from the core
news/runs/messages repository.

Tables are created by migration: 002_telegram_control_plane.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from psycopg2.extensions import connection as Connection


@dataclass(frozen=True)
class TelegramChat:
    chat_id: int
    chat_type: str
    chat_title: Optional[str]
    authorized: bool
    blocked: bool


@dataclass(frozen=True)
class TelegramAccessRequest:
    id: int
    chat_id: int
    status: str


def upsert_chat(
    conn: Connection, *, chat_id: int, chat_type: str, chat_title: Optional[str]
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO telegram_chats (chat_id, chat_type, chat_title)
            VALUES (%s, %s, %s)
            ON CONFLICT (chat_id) DO UPDATE
            SET chat_type = EXCLUDED.chat_type,
                chat_title = EXCLUDED.chat_title,
                updated_at = NOW()
            """,
            (chat_id, chat_type, chat_title),
        )
    conn.commit()


def get_chat(conn: Connection, *, chat_id: int) -> Optional[TelegramChat]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT chat_id, chat_type, chat_title, authorized, blocked
            FROM telegram_chats
            WHERE chat_id = %s
            """,
            (chat_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return TelegramChat(
            chat_id=int(row[0]),
            chat_type=str(row[1]),
            chat_title=row[2],
            authorized=bool(row[3]),
            blocked=bool(row[4]),
        )


def is_chat_authorized(conn: Connection, *, chat_id: int) -> bool:
    chat = get_chat(conn, chat_id=chat_id)
    return bool(chat and chat.authorized and not chat.blocked)


def create_access_request(
    conn: Connection,
    *,
    chat_id: int,
    requested_by_user_id: Optional[int],
    requested_by_username: Optional[str],
) -> tuple[TelegramAccessRequest, bool]:
    """Create an access request if none pending.

    Returns (request, was_created).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, chat_id, status
            FROM telegram_chat_requests
            WHERE chat_id = %s AND status = 'pending'
            """,
            (chat_id,),
        )
        existing = cur.fetchone()
        if existing:
            return TelegramAccessRequest(
                id=int(existing[0]), chat_id=int(existing[1]), status=str(existing[2])
            ), False

        cur.execute(
            """
            INSERT INTO telegram_chat_requests (chat_id, requested_by_user_id, requested_by_username)
            VALUES (%s, %s, %s)
            RETURNING id, chat_id, status
            """,
            (chat_id, requested_by_user_id, requested_by_username),
        )
        row = cur.fetchone()
    conn.commit()

    if not row:
        raise RuntimeError("Failed to create access request")

    return TelegramAccessRequest(id=int(row[0]), chat_id=int(row[1]), status=str(row[2])), True


def list_pending_access_requests(
    conn: Connection, *, limit: int = 20
) -> list[TelegramAccessRequest]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, chat_id, status
            FROM telegram_chat_requests
            WHERE status = 'pending'
            ORDER BY created_at ASC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()

    return [TelegramAccessRequest(id=int(r[0]), chat_id=int(r[1]), status=str(r[2])) for r in rows]


def approve_access_request(
    conn: Connection, *, request_id: int, approved_by_user_id: int
) -> Optional[int]:
    """Approve request. Returns chat_id if updated, else None."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE telegram_chat_requests
            SET status = 'approved',
                resolved_at = NOW(),
                resolved_by_user_id = %s
            WHERE id = %s AND status = 'pending'
            RETURNING chat_id
            """,
            (approved_by_user_id, request_id),
        )
        row = cur.fetchone()
        if not row:
            conn.commit()
            return None
        chat_id = int(row[0])

        cur.execute(
            """
            UPDATE telegram_chats
            SET authorized = TRUE,
                authorized_at = NOW(),
                authorized_by_user_id = %s,
                updated_at = NOW()
            WHERE chat_id = %s
            """,
            (approved_by_user_id, chat_id),
        )

    conn.commit()
    return chat_id


def deny_access_request(
    conn: Connection, *, request_id: int, denied_by_user_id: int, reason: Optional[str]
) -> Optional[int]:
    """Deny request. Returns chat_id if updated, else None."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE telegram_chat_requests
            SET status = 'denied',
                deny_reason = %s,
                resolved_at = NOW(),
                resolved_by_user_id = %s
            WHERE id = %s AND status = 'pending'
            RETURNING chat_id
            """,
            (reason, denied_by_user_id, request_id),
        )
        row = cur.fetchone()
    conn.commit()
    if not row:
        return None
    return int(row[0])


def set_subscription_enabled(
    conn: Connection,
    *,
    chat_id: int,
    stream_name: str,
    enabled: bool,
    actor_user_id: Optional[int],
) -> None:
    with conn.cursor() as cur:
        if enabled:
            cur.execute(
                """
                INSERT INTO telegram_stream_subscriptions (chat_id, stream_name, enabled, enabled_by_user_id, disabled_at)
                VALUES (%s, %s, TRUE, %s, NULL)
                ON CONFLICT (chat_id, stream_name) DO UPDATE
                SET enabled = TRUE,
                    enabled_at = NOW(),
                    enabled_by_user_id = EXCLUDED.enabled_by_user_id,
                    disabled_at = NULL
                """,
                (chat_id, stream_name, actor_user_id),
            )
        else:
            cur.execute(
                """
                UPDATE telegram_stream_subscriptions
                SET enabled = FALSE,
                    disabled_at = NOW()
                WHERE chat_id = %s AND stream_name = %s
                """,
                (chat_id, stream_name),
            )
    conn.commit()


def list_enabled_subscriptions(conn: Connection, *, chat_id: int) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT stream_name
            FROM telegram_stream_subscriptions
            WHERE chat_id = %s AND enabled = TRUE
            ORDER BY stream_name ASC
            """,
            (chat_id,),
        )
        rows = cur.fetchall()
    return [str(r[0]) for r in rows]


def list_broadcast_chat_ids(conn: Connection, *, stream_name: str) -> list[int]:
    """List authorized, enabled recipients for a stream.

    Recipients are chats that are:
    - subscribed to the given stream
    - enabled
    - authorized
    - not blocked

    Order is deterministic.
    """

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.chat_id
            FROM telegram_stream_subscriptions AS s
            JOIN telegram_chats AS c
              ON c.chat_id = s.chat_id
            WHERE s.stream_name = %s
              AND s.enabled = TRUE
              AND c.authorized = TRUE
              AND c.blocked = FALSE
            ORDER BY s.chat_id ASC
            """,
            (stream_name,),
        )
        rows = cur.fetchall()

    return [int(r[0]) for r in rows]


def get_bot_state(conn: Connection, *, key: str) -> Optional[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT value FROM telegram_bot_state WHERE key = %s", (key,))
        row = cur.fetchone()
    return str(row[0]) if row else None


def set_bot_state(conn: Connection, *, key: str, value: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO telegram_bot_state (key, value)
            VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value,
                updated_at = NOW()
            """,
            (key, value),
        )
    conn.commit()
