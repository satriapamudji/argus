"""LLM triage module for Argus scoring.

Uses OpenRouter API for optional LLM-based triage of news items.
This is a secondary scoring pass that can refine heuristic scores.
"""

import json
import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from argus.config import ScoringConfig
from argus.scoring.types import ScoringCandidate, ScoringResult

logger = logging.getLogger(__name__)

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# System prompt for news triage
TRIAGE_SYSTEM_PROMPT = """You are a financial news analyst triaging news items for a daily market update.

Your task is to evaluate each news item and return a JSON response with:
- relevance_score: 0-100 (how relevant is this for market participants?)
- urgency_score: 0-100 (how time-sensitive is this news?)
- quality_score: 0-100 (how reliable/well-sourced is this?)
- topic: one of [macro, earnings, geopolitics, markets, crypto, commodities, other]
- summary: one-sentence summary of why this matters (max 100 chars)
- include: boolean - should this be included in today's update?

Focus on:
- Market-moving potential
- Relevance to US equity investors
- Timeliness and freshness
- Source credibility

Respond ONLY with valid JSON, no other text."""

TRIAGE_USER_TEMPLATE = """Evaluate this news item:

Title: {title}
Source: {source}
Published: {published}
Snippet: {snippet}

Return JSON with: relevance_score, urgency_score, quality_score, topic, summary, include"""


@dataclass
class LLMTriageResult:
    """Result from LLM triage of a single item."""

    news_item_id: int
    relevance_score: int
    urgency_score: int
    quality_score: int
    topic: str
    summary: str
    include: bool
    raw_response: Optional[str] = None
    error: Optional[str] = None


class LLMTriager:
    """LLM-based news triage using OpenRouter API."""

    def __init__(
        self,
        config: ScoringConfig,
        http_client: Optional[httpx.Client] = None,
    ):
        """Initialize the LLM triager.

        Args:
            config: Scoring configuration with LLM settings.
            http_client: Optional httpx client for making requests.
        """
        self.config = config
        self.api_key = config.openrouter_api_key
        self.model = config.llm_model
        self._client = http_client
        self._owns_client = False

    def _get_client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.Client(timeout=30.0)
            self._owns_client = True
        return self._client

    def close(self) -> None:
        """Close HTTP client if we own it."""
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "LLMTriager":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def is_configured(self) -> bool:
        """Check if LLM triage is properly configured."""
        return bool(self.api_key) and self.config.llm_triage_enabled

    def triage_candidate(
        self,
        candidate: ScoringCandidate,
    ) -> LLMTriageResult:
        """Triage a single candidate using LLM.

        Args:
            candidate: The candidate to triage.

        Returns:
            LLMTriageResult with scores and recommendation.
        """
        if not self.is_configured():
            return LLMTriageResult(
                news_item_id=candidate.news_item_id,
                relevance_score=0,
                urgency_score=0,
                quality_score=0,
                topic="other",
                summary="",
                include=False,
                error="LLM triage not configured",
            )

        # Format the prompt
        user_prompt = TRIAGE_USER_TEMPLATE.format(
            title=candidate.title,
            source=candidate.source_name,
            published=candidate.published_at.isoformat() if candidate.published_at else "Unknown",
            snippet=candidate.snippet or "(no snippet)",
        )

        try:
            response = self._call_openrouter(user_prompt)
            return self._parse_response(candidate.news_item_id, response)
        except Exception as e:
            logger.warning(
                "LLM triage failed for item %d: %s",
                candidate.news_item_id,
                str(e),
            )
            return LLMTriageResult(
                news_item_id=candidate.news_item_id,
                relevance_score=0,
                urgency_score=0,
                quality_score=0,
                topic="other",
                summary="",
                include=False,
                error=str(e),
            )

    def _call_openrouter(self, user_prompt: str) -> str:
        """Make API call to OpenRouter.

        Args:
            user_prompt: The user message for the LLM.

        Returns:
            Raw response text from LLM.

        Raises:
            httpx.HTTPError: On API errors.
        """
        client = self._get_client()

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/argus-news",
            "X-Title": "Argus News Scoring",
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": TRIAGE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,  # Low temp for consistent scoring
            "max_tokens": 200,
        }

        response = client.post(
            OPENROUTER_API_URL,
            headers=headers,
            json=payload,
        )
        response.raise_for_status()

        data = response.json()
        return data["choices"][0]["message"]["content"]

    def _parse_response(
        self,
        news_item_id: int,
        response: str,
    ) -> LLMTriageResult:
        """Parse LLM response into structured result.

        Args:
            news_item_id: ID of the news item.
            response: Raw LLM response text.

        Returns:
            Parsed LLMTriageResult.
        """
        try:
            # Try to extract JSON from response
            # Handle markdown code blocks if present
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]

            data = json.loads(response.strip())

            return LLMTriageResult(
                news_item_id=news_item_id,
                relevance_score=int(data.get("relevance_score", 0)),
                urgency_score=int(data.get("urgency_score", 0)),
                quality_score=int(data.get("quality_score", 0)),
                topic=str(data.get("topic", "other")),
                summary=str(data.get("summary", ""))[:100],
                include=bool(data.get("include", False)),
                raw_response=response,
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning("Failed to parse LLM response: %s", str(e))
            return LLMTriageResult(
                news_item_id=news_item_id,
                relevance_score=0,
                urgency_score=0,
                quality_score=0,
                topic="other",
                summary="",
                include=False,
                raw_response=response,
                error=f"Parse error: {e}",
            )


def apply_llm_triage(
    results: list[ScoringResult],
    candidates: list[ScoringCandidate],
    config: ScoringConfig,
) -> list[ScoringResult]:
    """Apply LLM triage to top candidates and adjust scores.

    Only triages the top N candidates by heuristic score.
    LLM scores are blended with heuristic scores.

    Args:
        results: Heuristic scoring results (sorted by score desc).
        candidates: Original candidates (for context).
        config: Scoring configuration.

    Returns:
        Updated results with LLM triage applied.
    """
    if not config.llm_triage_enabled or not config.openrouter_api_key:
        logger.debug("LLM triage disabled or not configured")
        return results

    # Build candidate lookup
    candidate_map = {c.news_item_id: c for c in candidates}

    # Only triage top N candidates
    top_n = min(config.llm_max_items, len(results))
    to_triage = results[:top_n]

    logger.info("Running LLM triage on top %d candidates", top_n)

    with LLMTriager(config) as triager:
        for result in to_triage:
            candidate = candidate_map.get(result.news_item_id)
            if candidate is None:
                continue

            triage = triager.triage_candidate(candidate)

            if triage.error:
                logger.debug(
                    "LLM triage error for %d: %s",
                    result.news_item_id,
                    triage.error,
                )
                continue

            # Blend LLM scores with heuristic scores
            # Weight: 60% heuristic, 40% LLM
            llm_impact = (triage.relevance_score + triage.urgency_score) // 2
            result.impact_score = int(result.impact_score * 0.6 + llm_impact * 0.4)

            # Update quality/confidence from LLM
            result.quality_score = int(result.quality_score * 0.5 + triage.quality_score * 0.5)

            # Override topic if LLM is confident
            if triage.topic != "other":
                result.topic = triage.topic

            # Add LLM flag
            result.flags.append("llm_triaged")
            result.reasons.append(f"llm: {triage.summary}")

    # Re-sort after LLM adjustments
    results.sort(key=lambda r: r.impact_score, reverse=True)

    return results
