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
        self._client = httpx.Client(timeout=timeout_seconds)

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
    ) -> None:
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_web_page_preview,
        }
        resp = self._client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram sendMessage failed: {data}")
