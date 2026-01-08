from __future__ import annotations

from psycopg2.extensions import connection as Connection

from argus.config import ArgusConfig
from argus.ingestion.rss_worker import IngestionStats, RSSWorker


class RSSIngestionProvider:
    def run(self, *, config: ArgusConfig, conn: Connection) -> IngestionStats:
        allowlist = config.stream.rss.allowlist_files or []
        if len(allowlist) != 1:
            raise ValueError(
                "For providers.ingestion='rss', stream.rss.allowlist_files must contain exactly 1 file"
            )

        worker = RSSWorker(config=config, conn=conn)
        return worker.run()
