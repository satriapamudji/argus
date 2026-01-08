"""Minimal Telegram Bot API client used by the control-plane.

We intentionally keep this separate from publishing logic so the command receiver
can send small replies/notifications.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class TelegramBotApi:
    def __init__(self, *, bot_token: str, timeout_seconds: float = 30.0) -> None:
        self._bot_token = bot_token

        # Telegram long-polling (getUpdates) can legitimately hold the connection open for
        # `timeout` seconds. Ensure our HTTP client read timeout is comfortably above that.
        #
        # We keep other phases reasonably short to avoid hanging on connect/write.
        self._client = httpx.Client(
            timeout=httpx.Timeout(
                connect=10.0,
                read=max(timeout_seconds, 65.0),
                write=10.0,
                pool=10.0,
            )
        )

    def close(self) -> None:
        self._client.close()

    def get_updates(self, *, offset: Optional[int], timeout: int = 30) -> list[dict[str, Any]]:
        url = f"https://api.telegram.org/bot{self._bot_token}/getUpdates"
        payload: dict[str, Any] = {"timeout": timeout}
        if offset is not None:
            payload["offset"] = offset

        resp = self._client.get(url, params=payload)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram getUpdates failed: {data}")
        return list(data.get("result", []))

    def send_message(
        self,
        *,
        chat_id: int,
        text: str,
        parse_mode: str = "MarkdownV2",
        disable_web_page_preview: bool = True,
        reply_markup: Optional[dict[str, Any]] = None,
    ) -> None:
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_web_page_preview,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        resp = self._client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram sendMessage failed: {data}")
