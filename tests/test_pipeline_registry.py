from __future__ import annotations

from argus.config import ArgusConfig, StreamConfig, StreamProvidersConfig
from argus.pipeline.registry import (
    get_enrichment_provider,
    get_ingestion_provider,
    get_publisher_provider,
    get_scoring_provider,
)


def test_registry_defaults() -> None:
    cfg = ArgusConfig()
    stream = cfg.stream

    assert stream.providers.ingestion == "rss"
    assert stream.providers.scoring == "heuristic_v1"
    assert stream.providers.enrichment == "fetch_extract"
    assert stream.providers.publisher == "telegram"

    assert get_ingestion_provider(stream).__class__.__name__ == "RSSIngestionProvider"
    assert get_scoring_provider(stream).__class__.__name__ == "HeuristicV1ScoringProvider"
    assert get_enrichment_provider(stream).__class__.__name__ == "FetchExtractEnrichmentProvider"
    assert get_publisher_provider(stream).__class__.__name__ == "TelegramPublisherProvider"


def test_registry_publisher_null() -> None:
    stream = StreamConfig(providers=StreamProvidersConfig(publisher="null"))
    assert get_publisher_provider(stream).__class__.__name__ == "NullPublisherProvider"
