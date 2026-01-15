"""News scoring module for Argus.

Scores and ranks news items for each run window to select the best 2-6 items
using heuristics and optional LLM triage.
"""

from argus.scoring.heuristics import HeuristicScorer
from argus.scoring.heuristics_v2 import score_candidates_v2
from argus.scoring.heuristics_v3 import score_candidates_v3
from argus.scoring.types import ScoringCandidate, ScoringResult
from argus.scoring.worker import ScoringWorker, run_scoring

__all__ = [
    "HeuristicScorer",
    "ScoringCandidate",
    "ScoringResult",
    "ScoringWorker",
    "run_scoring",
    "score_candidates_v2",
    "score_candidates_v3",
]
