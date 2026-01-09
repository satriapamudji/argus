from __future__ import annotations

from psycopg2.extensions import connection as Connection

from argus.config import ArgusConfig
from argus.scoring.types import ScoringStats
from argus.scoring.worker import ScoringWorker


class HeuristicV2ScoringProvider:
    def run(
        self,
        *,
        config: ArgusConfig,
        conn: Connection,
        window_hours: int,
        dry_run: bool,
    ) -> ScoringStats:
        """Production v2 scoring provider with macro-first prioritization.

        This provider uses heuristic_v2 scoring which applies:
        - Domain-based tier scoring (Reuters/Bloomberg > CNBC > Yahoo/Nasdaq)
        - Author/provider penalties (Motley Fool, MarketBeat, RTTNews, etc.)
        - Nasdaq template penalties (ETF flow alerts, moving average, etc.)
        - Macro catalyst boosting (Fed/CPI/jobs/geopolitics)
        - Clickbait/listicle penalties
        - Preview vs outcome distinction
        """

        worker = ScoringWorker(
            config=config,
            conn=conn,
            window_hours=window_hours,
            dry_run=dry_run,
            use_v2=True,
        )
        try:
            return worker.run()
        finally:
            worker.close()
