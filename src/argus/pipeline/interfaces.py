"""Pipeline provider interfaces.

Providers are thin adapters around existing stage implementations.
They should:
- read required inputs from the DB
- write outputs to the DB (unless dry_run)
- return existing stats/result types

NOTE: Keep these signatures aligned with how the orchestrator runs today.
"""

from __future__ import annotations

from typing import Protocol

from psycopg2.extensions import connection as Connection

from argus.config import ArgusConfig
from argus.ingestion.rss_worker import IngestionStats
from argus.enrichment.worker import EnrichmentStats
from argus.publisher.types import PublishResult
from argus.scoring.types import ScoringStats


class IngestionProvider(Protocol):
    def run(self, *, config: ArgusConfig, conn: Connection) -> IngestionStats: ...


class ScoringProvider(Protocol):
    def run(
        self,
        *,
        config: ArgusConfig,
        conn: Connection,
        window_hours: int,
        dry_run: bool,
    ) -> ScoringStats: ...


class EnrichmentProvider(Protocol):
    def run(
        self,
        *,
        config: ArgusConfig,
        conn: Connection,
        window_hours: int,
    ) -> EnrichmentStats: ...


class PublisherProvider(Protocol):
    def publish(
        self,
        *,
        config: ArgusConfig,
        conn: Connection,
        message_id: int,
        dry_run: bool,
        silent: bool,
    ) -> PublishResult: ...
