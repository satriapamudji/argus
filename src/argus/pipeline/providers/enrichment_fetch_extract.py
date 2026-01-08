from __future__ import annotations

from psycopg2.extensions import connection as Connection

from argus.config import ArgusConfig
from argus.enrichment.worker import EnrichmentStats, EnrichmentWorker


class FetchExtractEnrichmentProvider:
    def run(
        self,
        *,
        config: ArgusConfig,
        conn: Connection,
        window_hours: int,
    ) -> EnrichmentStats:
        worker = EnrichmentWorker(
            config=config,
            conn=conn,
            window_hours=window_hours,
        )
        try:
            return worker.run()
        finally:
            # never close conn (owned by orchestrator), but follow worker lifecycle
            worker.close()
