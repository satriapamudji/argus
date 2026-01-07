"""Near-duplicate detection and topic diversity helpers.

This module provides:
- SimHash-based near-duplicate detection
- Hamming distance comparison
- Topic labeling (heuristic rules)
- Diversity helpers for facts bundle selection
"""

from argus.dedupe.simhash import (
    compute_simhash,
    hamming_distance,
    tokenize,
)
from argus.dedupe.near_duplicate import (
    check_near_duplicate,
    find_near_duplicates,
)
from argus.dedupe.topics import (
    TopicLabel,
    label_topic,
    TOPIC_KEYWORDS,
)
from argus.dedupe.diversity import (
    DiversityChecker,
    enforce_topic_diversity,
)

__all__ = [
    # SimHash
    "compute_simhash",
    "hamming_distance",
    "tokenize",
    # Near-duplicate detection
    "check_near_duplicate",
    "find_near_duplicates",
    # Topics
    "TopicLabel",
    "label_topic",
    "TOPIC_KEYWORDS",
    # Diversity
    "DiversityChecker",
    "enforce_topic_diversity",
]
