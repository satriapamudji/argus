from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import pytest

from argus.config import ArgusConfig
from argus.pipeline.providers.publisher_telegram import TelegramPublisherProvider
from argus.publisher.types import PublishResult


@dataclass(frozen=True)
class _FakeMessage:
    content: str


def _success_result(payload: dict, *, dry_run: bool) -> PublishResult:
    return PublishResult(
        success=True,
        telegram_message_id=123,
        published_at=datetime.now(timezone.utc) if not dry_run else None,
        error=None,
        dry_run=dry_run,
        payload=payload,
        retries=0,
        was_truncated=False,
        original_length=len(payload.get("text", "")),
    )


def _failure_result(payload: dict, *, dry_run: bool, error: str) -> PublishResult:
    return PublishResult(
        success=False,
        telegram_message_id=None,
        published_at=None,
        error=error,
        dry_run=dry_run,
        payload=payload,
        retries=0,
        was_truncated=False,
        original_length=len(payload.get("text", "")),
    )


def test_broadcast_publishes_to_all_recipients_best_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = TelegramPublisherProvider()

    telegram_cfg = object()
    config = cast(
        ArgusConfig,
        SimpleNamespace(stream=SimpleNamespace(name="us_markets", telegram=telegram_cfg)),
    )

    conn = MagicMock()

    monkeypatch.setattr(
        "argus.pipeline.providers.publisher_telegram.get_message_by_id",
        lambda _conn, _message_id: _FakeMessage(content="hello"),
    )

    monkeypatch.setattr(
        "argus.pipeline.providers.publisher_telegram.list_broadcast_chat_ids",
        lambda _conn, stream_name: [111, 222, 333],
    )

    update_calls: list[dict] = []

    def _update_message(_conn, **kwargs):
        update_calls.append(kwargs)

    monkeypatch.setattr(
        "argus.pipeline.providers.publisher_telegram.update_message", _update_message
    )

    sent_chat_ids: list[str] = []

    class _FakePublisher:
        def __init__(self, _cfg):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def publish(self, content: str, chat_id: str, silent: bool):
            sent_chat_ids.append(chat_id)
            if chat_id == "222":
                return _failure_result(
                    {"chat_id": chat_id, "text": content}, dry_run=False, error="nope"
                )
            return _success_result({"chat_id": chat_id, "text": content}, dry_run=False)

        def publish_dry_run(self, content: str, chat_id: str, silent: bool):
            raise AssertionError("not expected")

    monkeypatch.setattr(
        "argus.pipeline.providers.publisher_telegram.TelegramPublisher", _FakePublisher
    )

    result = provider.publish(
        config=cast(ArgusConfig, config),
        conn=conn,
        message_id=1,
        dry_run=False,
        silent=False,
    )

    assert result.success is True


def test_broadcast_dry_run_does_not_update_db(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = TelegramPublisherProvider()

    telegram_cfg = object()
    config = cast(
        ArgusConfig,
        SimpleNamespace(stream=SimpleNamespace(name="us_markets", telegram=telegram_cfg)),
    )

    conn = MagicMock()

    monkeypatch.setattr(
        "argus.pipeline.providers.publisher_telegram.get_message_by_id",
        lambda _conn, _message_id: _FakeMessage(content="hello"),
    )

    monkeypatch.setattr(
        "argus.pipeline.providers.publisher_telegram.list_broadcast_chat_ids",
        lambda _conn, stream_name: [111],
    )

    update_message_mock = MagicMock()
    monkeypatch.setattr(
        "argus.pipeline.providers.publisher_telegram.update_message", update_message_mock
    )

    class _FakePublisher:
        def __init__(self, _cfg):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def publish(self, content: str, chat_id: str, silent: bool):
            raise AssertionError("not expected")

        def publish_dry_run(self, content: str, chat_id: str, silent: bool):
            return _success_result({"chat_id": chat_id, "text": content}, dry_run=True)

    monkeypatch.setattr(
        "argus.pipeline.providers.publisher_telegram.TelegramPublisher", _FakePublisher
    )

    result = provider.publish(
        config=cast(ArgusConfig, config),
        conn=conn,
        message_id=1,
        dry_run=True,
        silent=False,
    )

    assert result.success is True
    assert result.dry_run is True
    update_message_mock.assert_not_called()
