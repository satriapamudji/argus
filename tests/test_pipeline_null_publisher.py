from __future__ import annotations

from types import SimpleNamespace

from argus.config import ArgusConfig
from argus.pipeline.providers.publisher_null import NullPublisherProvider


def test_null_publisher_marks_skipped(monkeypatch) -> None:
    # Avoid real DB access; assert update_message is invoked.
    called = SimpleNamespace(args=None, kwargs=None)

    def fake_update_message(*args, **kwargs):
        called.args = args
        called.kwargs = kwargs

    monkeypatch.setattr(
        "argus.pipeline.providers.publisher_null.update_message", fake_update_message
    )

    provider = NullPublisherProvider()
    result = provider.publish(
        config=ArgusConfig(),
        conn=None,  # type: ignore[arg-type]
        message_id=123,
        dry_run=False,
        silent=True,
    )

    assert result.success is True
    assert called.kwargs == {
        "conn": None,
        "message_id": 123,
        "publish_status": "skipped",
    }


def test_null_publisher_dry_run_does_not_touch_db(monkeypatch) -> None:
    def boom_update_message(*_args, **_kwargs):
        raise AssertionError("update_message should not be called in dry_run")

    monkeypatch.setattr(
        "argus.pipeline.providers.publisher_null.update_message", boom_update_message
    )

    provider = NullPublisherProvider()
    result = provider.publish(
        config=ArgusConfig(),
        conn=None,  # type: ignore[arg-type]
        message_id=123,
        dry_run=True,
        silent=True,
    )

    assert result.success is True
    assert result.dry_run is True
