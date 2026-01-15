"""Heuristic v3 scoring provider for Argus.

Crypto-first scoring provider using heuristic_v3 with protocol/exchange events,
market structure shifts, and technical signals.
"""

from __future__ import annotations

from psycopg2.extensions import connection as Connection

from argus.config import ArgusConfig
from argus.scoring.types import ScoringStats
from argus.scoring.worker import ScoringWorker


class HeuristicV3ScoringProvider:
    def run(
        self,
        *,
        config: ArgusConfig,
        conn: Connection,
        window_hours: int,
        dry_run: bool,
    ) -> ScoringStats:
        """Crypto-first scoring provider with v3 prioritization.

        This provider uses heuristic_v3 scoring which applies:
        - Protocol/exchange event boosting (hacks, regulation, ETFs)
        - Market structure shifts (DeFi TVL, funding rates, liquidations)
        - Technical signal boosting (ATH breaks, volume spikes)
        - Crypto media quality tiers (CoinDesk/TheBlock > aggregators)
        - Crypto-specific spam penalties (price predictions, moon talk)
        """

        worker = ScoringWorker(
            config=config,
            conn=conn,
            window_hours=window_hours,
            dry_run=dry_run,
            use_v3=True,
        )
        try:
            return worker.run()
        finally:
            worker.close()
