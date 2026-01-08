from __future__ import annotations

from psycopg2.extensions import connection as Connection

from argus.config import ArgusConfig
from argus.scoring.types import ScoringStats
from argus.scoring.worker import ScoringWorker


class HeuristicV1ScoringProvider:
    def run(
        self,
        *,
        config: ArgusConfig,
        conn: Connection,
        window_hours: int,
        dry_run: bool,
    ) -> ScoringStats:
        worker = ScoringWorker(
            config=config,
            conn=conn,
            window_hours=window_hours,
            dry_run=dry_run,
        )
        try:
            return worker.run()
        finally:
            # never close conn (owned by orchestrator), but follow worker lifecycle
            worker.close()
