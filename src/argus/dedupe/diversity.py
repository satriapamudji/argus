"""Topic diversity helpers for facts bundle selection.

Provides utilities to enforce diversity constraints like
"no 2 items from the same topic" during news selection.
"""

from collections import Counter
from dataclasses import dataclass
from typing import Optional, TypeVar

from argus.dedupe.topics import TopicLabel, get_topic_priority


@dataclass
class NewsItemForDiversity:
    """Minimal news item representation for diversity checking.

    This interface allows the diversity checker to work with any
    object that has these fields.
    """

    id: int
    topic: TopicLabel
    score: float  # Impact/relevance score for ranking


T = TypeVar("T")


class DiversityChecker:
    """Enforces topic diversity constraints on news selection.

    Configurable to allow at most N items per topic.
    """

    def __init__(self, max_per_topic: int = 1):
        """Initialize diversity checker.

        Args:
            max_per_topic: Maximum items allowed per topic (default 1).
        """
        self.max_per_topic = max_per_topic
        self._topic_counts: Counter[TopicLabel] = Counter()
        self._selected_ids: set[int] = set()

    def reset(self) -> None:
        """Reset the checker state for a new selection round."""
        self._topic_counts.clear()
        self._selected_ids.clear()

    def can_add(self, item: NewsItemForDiversity) -> bool:
        """Check if an item can be added without violating constraints.

        Args:
            item: News item to check.

        Returns:
            True if item can be added.
        """
        if item.id in self._selected_ids:
            return False
        return self._topic_counts[item.topic] < self.max_per_topic

    def add(self, item: NewsItemForDiversity) -> bool:
        """Add an item if it doesn't violate constraints.

        Args:
            item: News item to add.

        Returns:
            True if item was added, False if it would violate constraints.
        """
        if not self.can_add(item):
            return False

        self._topic_counts[item.topic] += 1
        self._selected_ids.add(item.id)
        return True

    def get_topic_counts(self) -> dict[TopicLabel, int]:
        """Get current topic counts.

        Returns:
            Dict mapping topic to count.
        """
        return dict(self._topic_counts)

    def get_selected_ids(self) -> set[int]:
        """Get IDs of selected items.

        Returns:
            Set of selected item IDs.
        """
        return self._selected_ids.copy()


def enforce_topic_diversity(
    items: list[NewsItemForDiversity],
    max_items: int,
    max_per_topic: int = 1,
    min_score: Optional[float] = None,
) -> list[NewsItemForDiversity]:
    """Select items while enforcing topic diversity.

    Selects the highest-scoring items while respecting the
    max_per_topic constraint.

    Args:
        items: List of candidate items (should be pre-sorted by score desc).
        max_items: Maximum total items to select.
        max_per_topic: Maximum items per topic (default 1 = no duplicates).
        min_score: Optional minimum score threshold.

    Returns:
        List of selected items respecting diversity constraints.
    """
    # Sort by score descending
    sorted_items = sorted(items, key=lambda x: x.score, reverse=True)

    # Filter by minimum score if specified
    if min_score is not None:
        sorted_items = [i for i in sorted_items if i.score >= min_score]

    checker = DiversityChecker(max_per_topic=max_per_topic)
    selected: list[NewsItemForDiversity] = []

    for item in sorted_items:
        if len(selected) >= max_items:
            break
        if checker.add(item):
            selected.append(item)

    return selected


def select_diverse_items_with_fallback(
    items: list[NewsItemForDiversity],
    max_items: int,
    max_per_topic: int = 1,
    fallback_max_per_topic: int = 2,
) -> list[NewsItemForDiversity]:
    """Select diverse items with fallback if not enough unique topics.

    If enforcing strict diversity (max_per_topic=1) doesn't yield
    enough items, relaxes the constraint to fallback_max_per_topic.

    Args:
        items: List of candidate items.
        max_items: Maximum total items to select.
        max_per_topic: Initial max items per topic.
        fallback_max_per_topic: Relaxed constraint if needed.

    Returns:
        List of selected items.
    """
    # Try strict diversity first
    selected = enforce_topic_diversity(items, max_items, max_per_topic)

    # If we don't have enough items, relax the constraint
    if len(selected) < max_items:
        selected = enforce_topic_diversity(items, max_items, fallback_max_per_topic)

    return selected


def compute_diversity_score(items: list[NewsItemForDiversity]) -> float:
    """Compute a diversity score for a selection of items.

    Score is based on how many unique topics are represented.
    Score of 1.0 = all items have unique topics.
    Score < 1.0 = some topics are repeated.

    Args:
        items: List of selected items.

    Returns:
        Diversity score between 0 and 1.
    """
    if not items:
        return 0.0

    unique_topics = len(set(item.topic for item in items))
    return unique_topics / len(items)


def rank_by_topic_priority(
    items: list[NewsItemForDiversity],
) -> list[NewsItemForDiversity]:
    """Rank items by their topic priority.

    Useful for breaking ties or secondary sorting after score.

    Args:
        items: List of items to rank.

    Returns:
        Items sorted by topic priority (highest first).
    """
    priorities = get_topic_priority()
    return sorted(items, key=lambda x: priorities.get(x.topic, 0), reverse=True)
