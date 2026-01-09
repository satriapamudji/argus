"""Heuristic scoring functions (v2) for Argus.

This module implements the production v2 scorer with macro-first prioritization.

Design goals:
- Deterministic scoring with domain-based tier resolution
- Penalty system for clickbait/low-signal content
- Macro-first category boosting (Fed/CPI/jobs/geopolitics)
- Author/provider quality signal for known low-signal publishers
- API-compatible with existing ScoringCandidate/ScoringResult types.

v2 strategy (macro-heavy us_close):
- Keep the v1 component breakdown as a baseline.
- Apply deterministic post-adjustments to the impact_score:
  * Penalize clickbait/listicles/pundit content (to push D-class items down).
  * Penalize known low-signal authors/providers (RTTNews, Motley Fool, etc.)
  * Penalize repeated "Stock Market Today"-style templates (spam constraint).
  * Penalize Nasdaq template families (ETF Inflow Alert, Moving Average, etc.)
  * Boost macro catalysts (Fed/CPI/jobs/geopolitics) so A-class items rise.
"""

from __future__ import annotations

import re
from typing import Optional

from argus.config import ScoringConfig
from argus.scoring.heuristics import HeuristicScorer
from argus.scoring.types import ScoringCandidate, ScoringResult


# ---------------------------------------------------------------------------
# Domain-based tier scoring (v2 feature)
# ---------------------------------------------------------------------------

# Domain tier configuration: maps normalized domains to tier scores
_DOMAIN_TIERS: dict[str, int] = {
    # Tier 1: Wire services, premier financial news (20 pts)
    "reuters.com": 20,
    "bloomberg.com": 20,
    "wsj.com": 20,
    "ft.com": 20,
    # Tier 2: Major financial media (15 pts)
    "cnbc.com": 15,
    "marketwatch.com": 15,
    "barrons.com": 15,
    # Tier 3: General financial coverage (10 pts)
    "yahoo.com": 10,
    "nasdaq.com": 10,
    "investing.com": 10,
}


def _get_domain_tier_score(domain: Optional[str]) -> int:
    """Get tier score for a domain (20/15/10/5)."""
    if not domain:
        return 5
    return _DOMAIN_TIERS.get(domain.lower(), 5)


# ---------------------------------------------------------------------------
# Author/Provider penalties (v2 feature - Task 23 immediate fix #1)
# ---------------------------------------------------------------------------

# Known low-signal providers/authors that syndicate through Nasdaq and other feeds.
# These often produce high-volume template content that crowds out macro news.
_AUTHOR_PENALTIES: dict[str, int] = {
    # Strong downrank: contributor/template content
    "the motley fool": 25,
    "motley fool": 25,
    "marketbeat": 20,
    "bnk invest": 22,
    "barchart": 15,
    # Moderate downrank: preview-heavy content
    "rttNews": 12,
    "rttnews": 12,
    # Contributor analysis (often low-signal)
    "zacks": 15,
    "tipranks": 12,
}


def _get_author_penalty(author: Optional[str]) -> tuple[int, Optional[str]]:
    """Get penalty for known low-signal authors.

    Returns:
        Tuple of (penalty_amount, author_key) or (0, None) if no match.
    """
    if not author:
        return 0, None
    author_lower = author.lower().strip()
    for key, penalty in _AUTHOR_PENALTIES.items():
        if key in author_lower:
            return penalty, key
    return 0, None


# ---------------------------------------------------------------------------
# Nasdaq template family penalties (v2 feature - Task 23 immediate fix #4)
# ---------------------------------------------------------------------------

_NASDAQ_TEMPLATE_PENALTIES: list[tuple[str, re.Pattern[str], int]] = [
    (
        "etf_flow_alert",
        re.compile(r"\b(etf\s+(in|out)flow\s+alert|big\s+etf\s+(in|out)flows?)\b", re.I),
        20,
    ),
    (
        "moving_average",
        re.compile(
            r"\b(breaks?\s+(above|below)\s+\d+[- ]?day\s+moving\s+average|crosses?\s+\d+[- ]?day\s+ma)\b",
            re.I,
        ),
        18,
    ),
    (
        "option_activity",
        re.compile(
            r"\b(noteworthy\s+.*\s+option\s+activity|unusual\s+options?\s+activity)\b", re.I
        ),
        15,
    ),
    (
        "technical_signal",
        re.compile(
            r"\b(technical\s+analysis|support\s+and\s+resistance|rsi\s+(overbought|oversold))\b",
            re.I,
        ),
        12,
    ),
]


# ---------------------------------------------------------------------------
# Post-adjustment patterns (kept intentionally small + high-signal)
# ---------------------------------------------------------------------------

# Mirrors eval_framework D patterns (but applied as a penalty rather than hard exclude).
# Keep these small + high-signal; they are a main lever for pushing noise out of Top20.
_D_PENALTIES: list[tuple[str, re.Pattern[str], int]] = [
    (
        "pundit_content",
        re.compile(
            r"\b(jim\s+cramer|cramer\s+says|motley\s+fool|seeking\s+alpha|mad\s+money)\b", re.I
        ),
        30,
    ),
    (
        "stock_picks",
        re.compile(
            r"\b(stocks?\s+to\s+buy|top\s+\d+\s+stocks?|best\s+(dividend\s+)?stocks?|should\s+you\s+buy|hot\s+stocks?)\b",
            re.I,
        ),
        25,
    ),
    (
        "fomo_bait",
        re.compile(
            r"\b(if\s+you('d|\s+had)\s+invested|millionaire[\s-]maker|could\s+(double|triple|10x)|get\s+rich|next\s+(amazon|apple|nvidia|tesla))\b",
            re.I,
        ),
        30,
    ),
    (
        "why_stock_moved",
        re.compile(
            r"\bwhy\b.*\b(stock|stocks|shares)\b.*\b("
            r"crash(?:ed)?|soar(?:ed)?|plung(?:ed|es)?|skyrocket(?:ed|s)?|"
            r"fell|fall(?:s|ing)?|jump(?:ed|s)?|surge(?:d|s)?|rose|rise(?:s|n)?|"
            r"drop(?:ped|s)?|slide(?:d|s)?|rall(?:ied|ies|y)|"
            r"tumble(?:d|s)?|sink(?:s|ing)?|tank(?:ed|s)?|slump(?:ed|s)?|"
            r"spike(?:d|s)?|pop(?:ped|s)?|blast(?:ed|s)?|"
            r"up|down|higher|lower"
            r")\b",
            re.I,
        ),
        20,
    ),
    # Task 23 fix #3: Tightened listicle pattern to avoid year false-positives.
    # Now requires explicit listicle words, not just "number + noun".
    (
        "listicle",
        re.compile(
            r"\b(\d+\s+reasons?\s+(why|to)|"
            r"\d+\s+best\s+(stocks?|ways?|things?)|"
            r"\d+\s+worst\s+(stocks?|things?)|"
            r"\d+\s+things?\s+to\s+(know|watch|buy)|"
            r"top\s+\d+\s+(reasons?|stocks?|picks?))\b",
            re.I,
        ),
        18,
    ),
    # Lighter listicle penalty - now more specific to avoid year matches like "2026"
    (
        "listicle_light",
        re.compile(
            r"\b([3-9]|1[0-9])\s+(stocks?|names?|ways?|reasons?|charts?|picks?)\s+(to|for|you)\b",
            re.I,
        ),
        8,
    ),
]

# Template-specific digest family used to enforce spam constraint (must stay <=1 in Top12).
_TEMPLATE_MARKET_TODAY = re.compile(r"\bstock\s+market\s+today\b", re.I)

# B/digest markers used for balancing (aligned to eval_framework B_KEYWORDS)
# Important: eval_framework classifies B if ANY B_KEYWORDS hit, and it includes
# generic tokens like "markets"/"stocks"/"shares". We intentionally keep v2's B detection
# narrower (rates/fx/commodities/index terms) to avoid boosting generic non-B content.
_B_DIGEST = re.compile(
    r"\b(s&p\s*500|nasdaq|dow|futures|vix|yields?|treasur(y|ies)|dollar\b|dxy\b|fx\b|forex|oil|crude|wti|brent|gold|silver|copper|natural\s+gas)\b",
    re.I,
)

# Extra B-boost markers (non-template): help pull real market digests into Top12 without
# letting "Stock Market Today" take over.
_B_BOOST = re.compile(
    r"\b(futures?|vix|s&p\s*500|nasdaq|dow|2-?year|10-?year|front\s+end|curve|yield\s+curve|yields?|treasur(y|ies)|bps|basis\s+points|dxy\b|dollar\b|dollar\s+index|fx\b|forex|brent|wti|oil|crude|gold|silver|copper|natural\s+gas)\b",
    re.I,
)

# Preview/anticipation penalties ("awaited" / "set to" / "expected")
_PREVIEW_PENALTY = re.compile(
    r"\b("
    r"expected|ahead\s+of|awaited|likely|"
    r"set\s+to|set\s+for|look\s+set\s+to|"
    r"seen\s+(higher|lower)|"
    r"what\s+to\s+watch|"
    r"in\s+focus|in\s+the\s+spotlight|"
    r"due\s+out|is\s+due|due\s+(today|this\s+week|this\s+month)"
    r")\b",
    re.I,
)

# Task 23 fix #2: Tightened outcome boost - require actual outcome context.
# Avoid false-positives on phrases like "rate-cut hopes" or "expected to cut".
_OUTCOME_BOOST = re.compile(
    r"\b("
    # Past-tense actions indicating something happened
    r"rose|fell|jumped|plunged|soared|surged|"
    r"accelerated|slowed|"
    r"came\s+in\s+at|"
    # Results language
    r"beats?\s+expectations?|missed\s+expectations?|topped\s+estimates?|fell\s+short|"
    # Policy/legal outcomes (past tense)
    r"ruled|announced|approved|blocked|struck\s+down|upheld|signed|enacted|"
    # Rate actions (require past tense or definite article)
    r"(the\s+fed\s+)?(cut|raised|hiked|paused)\s+(rates?|by)"
    r")\b",
    re.I,
)

# Speculation/hopes language - should NOT get outcome boost
_SPECULATION_MARKERS = re.compile(
    r"\b(hopes?|bets?|expectations?|may|might|could|should|likely|expected\s+to|seen\s+to)\b",
    re.I,
)

# Retrospective / low-urgency markers. Applied conservatively to reduce "last year" recaps.
_RETROSPECTIVE = re.compile(
    r"\b("
    r"last\s+(year|quarter|month|week)|"
    r"year[-\s]?to[-\s]?date|ytd|"
    r"in\s+20\d{2}|"
    r"in\s+(january|february|march|april|may|june|july|august|september|october|november|december)"
    r")\b",
    re.I,
)
_EQUITY_TERMS = re.compile(r"\b(stock|stocks|shares)\b", re.I)

# Earnings are frequent + low-signal unless systemic.
_EARNINGS_ROUTINE = re.compile(
    r"\b(beats?\s+estimates?|misses?\s+estimates?|tops?\s+expectations?|falls?\s+short|q[1-4]\s+(profit|earnings|results))\b",
    re.I,
)
_EARNINGS_SYSTEMIC = re.compile(
    r"\b(profit\s+warning|guidance\s+cut|guidance\s+lower|sector[-\s]wide|industry[-\s]wide|bellwether|mass\s+layoffs|restructuring|large\s+layoffs)\b",
    re.I,
)

# Policy outcome context: helps distinguish "tariff decision/refunds" from generic policy chatter.
_POLICY_OUTCOME_CONTEXT = re.compile(
    r"\b(supreme\s+court|court|judge|injunction|lawsuit|legal|refunds?|customs|deadline|upheld|struck\s+down|blocked)\b",
    re.I,
)

# Macro catalyst boosters (aligned to eval_framework A_KEYWORDS buckets)
# We keep these conservative to avoid turning generic market wraps into A.
# Task 23 fix #5: Added trade deficit/balance terms
_MACRO_BOOSTERS: list[tuple[re.Pattern[str], int]] = [
    (re.compile(r"\b(fed|federal\s+reserve|fomc|powell)\b", re.I), 10),
    (re.compile(r"\b(cpi|pce|inflation|deflation)\b", re.I), 8),
    (re.compile(r"\b(nonfarm|payrolls|jobs\s+report|jobless\s+claims|unemployment)\b", re.I), 8),
    (re.compile(r"\b(gdp|ism|pmi)\b", re.I), 6),
    # Task 23 fix #5: Trade data releases
    (
        re.compile(
            r"\b(trade\s+(deficit|balance|surplus)|current\s+account|import|export)\b", re.I
        ),
        6,
    ),
    # Policy/geopolitics is often noisy; keep this lower to avoid crowding out true digest B.
    (re.compile(r"\b(tariff|tariffs|sanctions|embargo|trade\s+war|invasion)\b", re.I), 2),
    (re.compile(r"\b(opec\+?|hormuz|supply\s+disruption)\b", re.I), 6),
]


def _text(candidate: ScoringCandidate) -> str:
    parts = [candidate.title]
    if candidate.snippet:
        parts.append(candidate.snippet)
    return " ".join(parts).lower()


def _apply_post_adjustments(candidate: ScoringCandidate, base: ScoringResult) -> ScoringResult:
    text = _text(candidate)

    original_score = base.impact_score
    adj = 0

    is_template_market_today = _TEMPLATE_MARKET_TODAY.search(text) is not None
    is_preview = _PREVIEW_PENALTY.search(text) is not None
    is_outcome = _OUTCOME_BOOST.search(text) is not None
    is_speculation = _SPECULATION_MARKERS.search(text) is not None

    # Task 23 fix #2: Don't give outcome boost if speculation markers present
    if is_outcome and is_speculation:
        is_outcome = False

    # ---------------------------------------------------------------------------
    # Author/provider penalty (Task 23 fix #1)
    # ---------------------------------------------------------------------------
    author_penalty, author_key = _get_author_penalty(candidate.author)
    if author_penalty > 0:
        adj -= author_penalty
        base.flags.append(f"v2_penalty:author:{author_key}")

    # ---------------------------------------------------------------------------
    # Nasdaq template penalties (Task 23 fix #4)
    # ---------------------------------------------------------------------------
    for name, rx, penalty in _NASDAQ_TEMPLATE_PENALTIES:
        if rx.search(text):
            adj -= penalty
            base.flags.append(f"v2_penalty:nasdaq_template:{name}")

    # ---------------------------------------------------------------------------
    # Clickbait/noise penalties
    # ---------------------------------------------------------------------------
    for name, rx, penalty in _D_PENALTIES:
        if rx.search(text):
            adj -= penalty
            base.flags.append(f"v2_penalty:clickbait:{name}")

    # Penalize repeated template families (directly targets spam constraint in Top12).
    # NOTE: we apply only a mild per-item penalty here; de-duplication happens in a second pass.
    if is_template_market_today:
        adj -= 10
        base.flags.append("v2_penalty:template_market_today")
        base.flags.append("v2_template:market_today")

    # Prefer "what happened" over previews.
    if is_preview and not is_outcome:
        adj -= 20
        base.flags.append("v2_penalty:preview_only")
    elif is_preview and is_outcome:
        # Many real releases mention expectations; keep this light.
        adj -= 4
        base.flags.append("v2_penalty:preview_and_outcome")

    if is_outcome:
        adj += 8
        base.flags.append("v2_boost:outcome")

    # Boost macro catalysts.
    macro_strong_hits = 0
    macro_policy_hits = 0
    policy_context = _POLICY_OUTCOME_CONTEXT.search(text) is not None
    for rx, boost in _MACRO_BOOSTERS:
        if rx.search(text):
            adj += boost
            if boost >= 6:
                macro_strong_hits += 1
            else:
                macro_policy_hits += 1

    # Earnings: routine beats/misses are frequent; downrank unless systemic.
    if (
        _EARNINGS_ROUTINE.search(text)
        and not _EARNINGS_SYSTEMIC.search(text)
        and macro_strong_hits == 0
    ):
        adj -= 10
        base.flags.append("v2_penalty:routine_earnings")

    # Retrospectives ("last year", "in 2025") are usually low-urgency in a us_close feed.
    # Apply only when equity-ish AND not clearly macro.
    if _RETROSPECTIVE.search(text) and _EQUITY_TERMS.search(text) and macro_strong_hits == 0:
        adj -= 8
        base.flags.append("v2_penalty:retrospective")

    # Extra boost for policy outcomes (tariff legality/refunds) while keeping previews capped.
    policy_outcome = (macro_policy_hits > 0) and (policy_context or is_outcome)
    if policy_outcome and not (is_preview and not is_outcome):
        adj += 6
        base.flags.append("v2_boost:policy_outcome")

    # B promotion: push real market digests (rates/fx/commodities/index moves)
    # into the top band so Top12 can hit B>=4.
    # Keep this separate from the template family penalty above.
    if macro_strong_hits == 0 and _B_BOOST.search(text) and not is_template_market_today:
        adj += 14
        base.flags.append("v2_boost:market_digest")

    score = original_score + adj

    # If there are NO macro hits, apply a mild cap to avoid non-macro general content
    # dominating the top of a macro-heavy run.
    # Give true digest-y B items a higher cap, but still keep it below strong macro A.
    macro_floor_hits = macro_strong_hits + (macro_policy_hits if policy_outcome else 0)

    # Preview-only items should never get macro floors and should not crowd the very top.
    if is_preview and not is_outcome:
        score = min(score, 45)
    else:
        # If we have macro hits, ensure a minimum floor so true macro items don't get stuck.
        if macro_floor_hits >= 2:
            score = max(score, 40)
        if macro_floor_hits >= 3:
            score = max(score, 45)

        # Soft cap on macro to avoid Top12 becoming all-A.
        if macro_floor_hits >= 1:
            score = min(score, 60)

    # Template recaps are allowed, but shouldn't pin the top.
    if is_template_market_today:
        score = min(score, 52)

    if macro_floor_hits == 0:
        if _B_DIGEST.search(text):
            score = min(score, 58)
        else:
            score = min(score, 44)

    # Clamp final score to 0..100
    base.impact_score = max(0, min(100, int(score)))

    # Tag v2.
    base.scorer_version = "heuristic_v2"

    # Add brief reason for visibility (keep short; avoid noisy lists)
    delta = base.impact_score - original_score
    if delta != 0:
        base.reasons.append(f"v2_adjust:{delta:+d}")

    return base


def score_candidates_v2(
    candidates: list[ScoringCandidate],
    config: ScoringConfig,
    recent_simhashes: Optional[list[int]] = None,
) -> list[ScoringResult]:
    """Score a batch of candidates using heuristic v2.

    This is a pure function over the provided candidates. It does not read/write
    the database.

    Returns:
        List of ScoringResults, sorted by impact_score descending.
    """
    scorer = HeuristicScorer(config)
    if recent_simhashes:
        scorer.set_recent_simhashes(recent_simhashes)

    results: list[ScoringResult] = []
    for c in candidates:
        r = scorer.score_candidate(c)
        r = _apply_post_adjustments(c, r)
        results.append(r)

    # Enforce the "allow 1, crush the rest" rule for repeated template families.
    # This targets the eval spam constraint without nuking all market wrap recaps.
    market_today = [r for r in results if "v2_template:market_today" in r.flags]
    if len(market_today) > 1:
        market_today.sort(key=lambda r: (r.impact_score, r.news_item_id), reverse=True)
        for r in market_today[1:]:
            before = r.impact_score
            r.impact_score = max(0, r.impact_score - 35)
            r.flags.append("v2_penalty:template_market_today_dup")
            if r.impact_score != before:
                r.reasons.append(f"v2_adjust:{r.impact_score - before:+d}")

    results.sort(key=lambda r: r.impact_score, reverse=True)
    return results
