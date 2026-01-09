from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from argus.config import ArgusConfig


def _write_yaml(tmpdir: Path, content: str) -> Path:
    path = tmpdir / "config.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def test_providers_defaults() -> None:
    with tempfile.TemporaryDirectory() as d:
        tmpdir = Path(d)
        cfg_path = _write_yaml(
            tmpdir,
            """
stream:
  name: us_markets
  rss:
    allowlist_files:
      - rss/us_markets.txt
""".lstrip(),
        )

        cfg = ArgusConfig.load(cfg_path)
        assert cfg.stream.providers.ingestion == "rss"
        assert cfg.stream.providers.scoring == "heuristic_v2"
        assert cfg.stream.providers.enrichment == "fetch_extract"
        assert cfg.stream.providers.publisher == "telegram"


def test_providers_override() -> None:
    with tempfile.TemporaryDirectory() as d:
        tmpdir = Path(d)
        cfg_path = _write_yaml(
            tmpdir,
            """
stream:
  name: us_markets
  providers:
    ingestion: rss
  rss:
    allowlist_files:
      - rss/a.txt
      - rss/b.txt
""".lstrip(),
        )

        cfg = ArgusConfig.load(cfg_path)
        assert cfg.stream.providers.ingestion == "rss"
        assert cfg.stream.rss.allowlist_files == ["rss/a.txt", "rss/b.txt"]
