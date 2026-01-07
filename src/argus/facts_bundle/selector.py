"""Bundle selector with topic and source diversity constraints.

Selects news items for the facts bundle while enforcing:
1. Topic diversity: max N items per topic
2. Source diversity: max M items per source
3. Score ranking: prefer higher-scoring items
4. Content bonus: prefer items with enriched content
"""

from collections import Counter
from typing import Optional

from argus.facts_bundle.types import BundleCandidate, NewsItemBundle


class BundleSelector:
    """Selects items for bundle with diversity constraints.

    Enforces both topic-level and source-level diversity to ensure
    a balanced, varied news bundle.
    """

    def __init__(
        self,
        max_per_topic: int = 1,
        max_per_source: int = 2,
        enriched_bonus: int = 5,
    ) -> None:
        """Initialize the bundle selector.

        Args:
            max_per_topic: Maximum items allowed per topic (default 1).
            max_per_source: Maximum items allowed per source (default 2).
            enriched_bonus: Score bonus for items with enriched content.
        """
        self.max_per_topic = max_per_topic
        self.max_per_source = max_per_source
        self.enriched_bonus = enriched_bonus

        self._topic_counts: Counter[str] = Counter()
        self._source_counts: Counter[str] = Counter()
        self._selected_ids: set[int] = set()

        # Stats for reporting
        self._skipped_by_topic = 0
        self._skipped_by_source = 0

    def reset(self) -> None:
        """Reset selector state for a new selection round."""
        self._topic_counts.clear()
        self._source_counts.clear()
        self._selected_ids.clear()
        self._skipped_by_topic = 0
        self._skipped_by_source = 0

    def _normalize_source(self, source_name: str) -> str:
        """Normalize source name for comparison.

        Handles variations like 'Reuters' vs 'reuters.com'.
        """
        return source_name.lower().strip()

    def _normalize_topic(self, topic: Optional[str]) -> str:
        """Normalize topic for comparison.

        Treats None/empty as 'other'.
        """
        if not topic:
            return "other"
        return topic.lower().strip()

    def can_add(self, candidate: BundleCandidate) -> tuple[bool, Optional[str]]:
        """Check if a candidate can be added without violating constraints.

        Args:
            candidate: News item candidate to check.

        Returns:
            Tuple of (can_add, reason_if_not). reason is None if can add.
        """
        if candidate.news_item_id in self._selected_ids:
            return False, "already_selected"

        topic = self._normalize_topic(candidate.topic)
        source = self._normalize_source(candidate.source_name)

        if self._topic_counts[topic] >= self.max_per_topic:
            return False, "topic_limit"

        if self._source_counts[source] >= self.max_per_source:
            return False, "source_limit"

        return True, None

    def add(self, candidate: BundleCandidate) -> bool:
        """Add a candidate if it doesn't violate constraints.

        Args:
            candidate: News item candidate to add.

        Returns:
            True if candidate was added, False if it would violate constraints.
        """
        can_add, reason = self.can_add(candidate)
        if not can_add:
            if reason == "topic_limit":
                self._skipped_by_topic += 1
            elif reason == "source_limit":
                self._skipped_by_source += 1
            return False

        topic = self._normalize_topic(candidate.topic)
        source = self._normalize_source(candidate.source_name)

        self._topic_counts[topic] += 1
        self._source_counts[source] += 1
        self._selected_ids.add(candidate.news_item_id)
        return True

    def select(
        self,
        candidates: list[BundleCandidate],
        min_items: int = 2,
        max_items: int = 6,
    ) -> list[BundleCandidate]:
        """Select candidates respecting diversity constraints.

        Selection algorithm:
        1. Sort by effective_score DESC, news_item_id ASC (deterministic)
        2. Iterate through sorted candidates
        3. Add if doesn't violate topic or source constraints
        4. Stop when max_items reached or candidates exhausted

        Args:
            candidates: List of candidates to select from.
            min_items: Minimum items to select (will relax constraints if needed).
            max_items: Maximum items to select.

        Returns:
            List of selected candidates.
        """
        self.reset()

        # Sort by effective_score DESC, then id ASC for determinism
        sorted_candidates = sorted(
            candidates,
            key=lambda c: (-c.effective_score, c.news_item_id),
        )

        selected: list[BundleCandidate] = []

        for candidate in sorted_candidates:
            if len(selected) >= max_items:
                break
            if self.add(candidate):
                selected.append(candidate)

        # If we don't have enough items, relax constraints
        if len(selected) < min_items:
            selected = self._select_with_relaxed_constraints(
                sorted_candidates, min_items, max_items
            )

        return selected

    def _select_with_relaxed_constraints(
        self,
        sorted_candidates: list[BundleCandidate],
        min_items: int,
        max_items: int,
    ) -> list[BundleCandidate]:
        """Select with progressively relaxed constraints.

        Tries:
        1. Original constraints (already failed)
        2. max_per_topic = 2
        3. max_per_source = 3
        4. Both relaxed

        Args:
            sorted_candidates: Pre-sorted candidate list.
            min_items: Minimum items to select.
            max_items: Maximum items to select.

        Returns:
            List of selected candidates.
        """
        relaxation_stages = [
            (2, self.max_per_source),  # Relax topic first
            (self.max_per_topic, 3),  # Relax source
            (2, 3),  # Relax both
            (3, 4),  # More relaxed
        ]

        for max_topic, max_source in relaxation_stages:
            self.reset()
            original_topic = self.max_per_topic
            original_source = self.max_per_source
            self.max_per_topic = max_topic
            self.max_per_source = max_source

            selected: list[BundleCandidate] = []
            for candidate in sorted_candidates:
                if len(selected) >= max_items:
                    break
                if self.add(candidate):
                    selected.append(candidate)

            # Restore original constraints
            self.max_per_topic = original_topic
            self.max_per_source = original_source

            if len(selected) >= min_items:
                return selected

        # Last resort: just take top items by score
        self.reset()
        return sorted_candidates[:max_items]

    def get_topic_counts(self) -> dict[str, int]:
        """Get current topic counts.

        Returns:
            Dict mapping normalized topic to count.
        """
        return dict(self._topic_counts)

    def get_source_counts(self) -> dict[str, int]:
        """Get current source counts.

        Returns:
            Dict mapping normalized source to count.
        """
        return dict(self._source_counts)

    def get_stats(self) -> dict[str, int]:
        """Get selection statistics.

        Returns:
            Dict with skipped counts.
        """
        return {
            "selected": len(self._selected_ids),
            "skipped_by_topic": self._skipped_by_topic,
            "skipped_by_source": self._skipped_by_source,
        }


def select_bundle_items(
    candidates: list[BundleCandidate],
    max_per_topic: int = 1,
    max_per_source: int = 2,
    min_items: int = 2,
    max_items: int = 6,
) -> tuple[list[NewsItemBundle], dict[str, int]]:
    """Convenience function to select and convert bundle items.

    Args:
        candidates: List of candidates to select from.
        max_per_topic: Maximum items per topic.
        max_per_source: Maximum items per source.
        min_items: Minimum items to select.
        max_items: Maximum items to select.

    Returns:
        Tuple of (selected NewsItemBundle list, selection stats dict).
    """
    selector = BundleSelector(
        max_per_topic=max_per_topic,
        max_per_source=max_per_source,
    )

    selected_candidates = selector.select(
        candidates=candidates,
        min_items=min_items,
        max_items=max_items,
    )

    # Convert to immutable NewsItemBundle
    news_items = [c.to_news_item_bundle() for c in selected_candidates]

    stats = selector.get_stats()
    stats["enriched_items"] = sum(1 for c in selected_candidates if c.has_content)

    return news_items, stats
