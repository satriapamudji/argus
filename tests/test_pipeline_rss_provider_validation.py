from __future__ import annotations

import pytest

from argus.config import ArgusConfig
from argus.pipeline.providers.ingestion_rss import RSSIngestionProvider


def test_rss_ingestion_provider_requires_exactly_one_allowlist_file() -> None:
    provider = RSSIngestionProvider()

    cfg = ArgusConfig()
    cfg.stream.rss.allowlist_files = []

    # Avoid DB work: provider should validate before instantiating/using RSSWorker.
    with pytest.raises(ValueError, match="allowlist_files must contain exactly 1"):
        provider.run(config=cfg, conn=None)  # type: ignore[arg-type]

    cfg.stream.rss.allowlist_files = ["rss/a.txt", "rss/b.txt"]
    with pytest.raises(ValueError, match="allowlist_files must contain exactly 1"):
        provider.run(config=cfg, conn=None)  # type: ignore[arg-type]
