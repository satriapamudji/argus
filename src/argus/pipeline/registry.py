"""Provider registry for per-stream pipeline stage selection."""

from __future__ import annotations

from dataclasses import dataclass

from argus.config import StreamConfig
from argus.pipeline.interfaces import (
    EnrichmentProvider,
    IngestionProvider,
    PublisherProvider,
    ScoringProvider,
)
from argus.pipeline.providers.enrichment_fetch_extract import FetchExtractEnrichmentProvider
from argus.pipeline.providers.ingestion_rss import RSSIngestionProvider
from argus.pipeline.providers.publisher_null import NullPublisherProvider
from argus.pipeline.providers.publisher_telegram import TelegramPublisherProvider
from argus.pipeline.providers.scoring_heuristic_v1 import HeuristicV1ScoringProvider


@dataclass(frozen=True)
class ResolvedProviders:
    ingestion: IngestionProvider
    scoring: ScoringProvider
    enrichment: EnrichmentProvider
    publisher: PublisherProvider


def _require_key(*, stage: str, key: str, supported: set[str]) -> None:
    if key not in supported:
        raise ValueError(
            f"Unsupported provider for {stage}: '{key}'. Supported: {sorted(supported)}"
        )


def get_ingestion_provider(stream: StreamConfig) -> IngestionProvider:
    key = stream.providers.ingestion
    supported = {"rss"}
    _require_key(stage="ingestion", key=key, supported=supported)

    if key == "rss":
        return RSSIngestionProvider()

    raise AssertionError("unreachable")


def get_scoring_provider(stream: StreamConfig) -> ScoringProvider:
    key = stream.providers.scoring
    supported = {"heuristic_v1"}
    _require_key(stage="scoring", key=key, supported=supported)

    if key == "heuristic_v1":
        return HeuristicV1ScoringProvider()

    raise AssertionError("unreachable")


def get_enrichment_provider(stream: StreamConfig) -> EnrichmentProvider:
    key = stream.providers.enrichment
    supported = {"fetch_extract"}
    _require_key(stage="enrichment", key=key, supported=supported)

    if key == "fetch_extract":
        return FetchExtractEnrichmentProvider()

    raise AssertionError("unreachable")


def get_publisher_provider(stream: StreamConfig) -> PublisherProvider:
    key = stream.providers.publisher
    supported = {"telegram", "null"}
    _require_key(stage="publisher", key=key, supported=supported)

    if key == "telegram":
        return TelegramPublisherProvider()
    if key == "null":
        return NullPublisherProvider()

    raise AssertionError("unreachable")


def resolve_providers(stream: StreamConfig) -> ResolvedProviders:
    return ResolvedProviders(
        ingestion=get_ingestion_provider(stream),
        scoring=get_scoring_provider(stream),
        enrichment=get_enrichment_provider(stream),
        publisher=get_publisher_provider(stream),
    )
