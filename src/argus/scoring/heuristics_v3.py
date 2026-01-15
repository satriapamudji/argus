"""Heuristic scoring functions (v3) for Argus.

This module implements the crypto-specific v3 scorer with crypto-first prioritization.

Design goals:
- Deterministic scoring with crypto-domain-based tier resolution
- Protocol/exchange event boosting (hacks, regulation, ETFs)
- Market structure shifts (DeFi TVL, funding rates, liquidations)
- Technical signal boosting (ATH breaks, volume spikes)
- Crypto media quality tiers (CoinDesk/TheBlock > aggregators)
- Crypto-specific spam penalties (price predictions, moon talk)
- API-compatible with existing ScoringCandidate/ScoringResult types.

v3 strategy (crypto-first):
- Keep the v1 component breakdown as a baseline
- Apply deterministic post-adjustments to the impact_score:
  * Boost protocol/exchange events (hacks, regulation, ETF approvals)
  * Boost market structure shifts (DeFi TVL, funding rates, on-chain metrics)
  * Boost technical signals (ATH breaks, volume spikes, liquidations)
  * Penalize crypto-specific spam (price predictions, "to the moon", shilling)
  * Penalize generic market wraps ("daily crypto update", "crypto recap")
  * Crypto media quality tiers (CoinDesk/TheBlock = 20, Cointelegraph = 15)
"""

from __future__ import annotations

import re
from typing import Optional

from argus.config import ScoringConfig
from argus.scoring.heuristics import HeuristicScorer
from argus.scoring.types import ScoringCandidate, ScoringResult


# ---------------------------------------------------------------------------
# Domain-based tier scoring (v3 crypto-specific)
# ---------------------------------------------------------------------------

# Crypto domain tier configuration: maps normalized domains to tier scores
_CRYPTO_DOMAIN_TIERS: dict[str, int] = {
    # Tier 1: Premier crypto news (20 pts)
    "coindesk.com": 20,
    "theblock.co": 20,
    "decrypt.co": 20,
    # Tier 2: Major crypto media (15 pts)
    "cointelegraph.com": 15,
    "bitcoinmagazine.com": 15,
    # Tier 3: General/Aggregator coverage (10 pts)
    "yahoo.com": 10,
    "cryptobriefing.com": 10,
    # Tier 4: Everything else (5 pts)
}


def _get_crypto_domain_tier_score(domain: Optional[str]) -> int:
    """Get tier score for a crypto domain (20/15/10/5)."""
    if not domain:
        return 5
    return _CRYPTO_DOMAIN_TIERS.get(domain.lower(), 5)


# ---------------------------------------------------------------------------
# Crypto topic detection (7 subtopics)
# ---------------------------------------------------------------------------

_CRYPTO_TOPICS: dict[str, list[str]] = {
    "protocol_risk": [
        "hack", "exploit", "drain", "vulnerability", "suspension",
        "insolvency", "bankruptcy", "cefi", "exchange",
        "bridge", "smart contract", "reorg", "attack",
    ],
    "regulation": [
        "sec", "cftc", "regulation", "lawsuit", "approval", "etf",
        "compliance", "ban", "license", "enforcement", "legal",
        "commission", "regulator", "authority", "legislation",
    ],
    "defi": [
        "defi", "tvl", "total value locked", "uniswap", "aave", "curve",
        "liquidity", "yield farming", "staking", "validator",
        "protocol", "dex", "amm", "pool", "vault",
    ],
    "derivatives": [
        "funding rate", "open interest", "liquidation", "leverage",
        "perpetual", "futures", "options", "derivatives",
        "margin", "short", "long", "position",
    ],
    "onchain": [
        "whale", "hodl", "hash rate", "difficulty", "halving",
        "mining", "miner", "pool", "on-chain", "address",
        "transaction", "block", "confirmation",
    ],
    "technical": [
        "resistance", "support", "ath", "all-time high", "breakout",
        "rally", "surge", "plunge", "crash", "dump", "pump", "recovery",
        "correction", "consolidation", "volatility",
    ],
    "asset_news": [
        "bitcoin", "btc", "ethereum", "eth", "solana", "sol",
        "cardano", "ada", "ripple", "xrp", "dogecoin", "doge",
        "polkadot", "dot", "avalanche", "avax",
    ],
}

# Topic priority order (highest first)
_TOPIC_PRIORITY = [
    "protocol_risk",
    "regulation",
    "defi",
    "derivatives",
    "onchain",
    "technical",
    "asset_news",
]


def _detect_crypto_topic(text: str) -> Optional[str]:
    """Detect crypto topic from text.

    Returns the highest-priority topic that matches, or None if no matches.
    """
    text_lower = text.lower()
    for topic in _TOPIC_PRIORITY:
        keywords = _CRYPTO_TOPICS[topic]
        for keyword in keywords:
            if keyword in text_lower:
                return topic
    return None


# ---------------------------------------------------------------------------
# Crypto boosters (protocol events, market structure, technical)
# ---------------------------------------------------------------------------

# Protocol/exchange event boosters (highest priority)
_CRYPTO_PROTOCOL_BOOSTERS: list[tuple[str, re.Pattern[str], int]] = [
    (
        "hack_exploit",
        re.compile(
            r"\b(hack|exploit|drain|theft|vulnerability|breach|attack)\b",
            re.I,
        ),
        30,
    ),
    (
        "regulatory_approval",
        re.compile(
            r"\b(sec\s+approves|etf\s+approval|bitcoin\s+etf|ethereum\s+etf|"
            r"regulatory\s+approval|license\s+granted)\b",
            re.I,
        ),
        25,
    ),
    (
        "exchange_suspension",
        re.compile(
            r"\b(withdrawal\s+suspend|deposit\s+suspend|halt|pause|"
            r"suspend|maintenance| outage)\b",
            re.I,
        ),
        20,
    ),
    (
        "insolvency_bankruptcy",
        re.compile(
            r"\b(insolvency|bankruptcy|chapter\s+11|cease\s+trading|"
            r"freeze\s+assets)\b",
            re.I,
        ),
        28,
    ),
]

# Market structure shift boosters
_CRYPTO_MARKET_STRUCTURE_BOOSTERS: list[tuple[str, re.Pattern[str], int]] = [
    (
        "tvl_change",
        re.compile(
            r"\b(tvl|total\s+value\s+locked)\b.*(surge|plunge|drop|rise|hit|reach)",
            re.I,
        ),
        15,
    ),
    (
        "funding_rate",
        re.compile(
            r"\b(funding\s+rate|open\s+interest)\b.*(high|low|spike|surge|record)",
            re.I,
        ),
        14,
    ),
    (
        "liquidation",
        re.compile(
            r"\b(\$\d+[bm]?\s+)?liquidation(s)?\b",
            re.I,
        ),
        16,
    ),
    (
        "whale_movement",
        re.compile(
            r"\bwhale\b.*(buy|sell|move|transfer|deposit|withdraw)",
            re.I,
        ),
        12,
    ),
]

# Technical signal boosters
_CRYPTO_TECHNICAL_BOOSTERS: list[tuple[str, re.Pattern[str], int]] = [
    (
        "ath_break",
        re.compile(
            r"\b(ath|all-time\s+high|record\s+high|new\s+high)\b",
            re.I,
        ),
        12,
    ),
    (
        "volume_spike",
        re.compile(
            r"\bvolume\s+(spike|surge|record|unusual)\b",
            re.I,
        ),
        10,
    ),
    (
        "price_action",
        re.compile(
            r"\b(breaks?\s+(above|below)\$\d+|surge|plunge|rally|dump)\b",
            re.I,
        ),
        8,
    ),
]

# Breaking news bypass (boost regardless of domain)
_BREAKING_NEWS_BOOST = 15


# ---------------------------------------------------------------------------
# Crypto penalties (spam, noise, low-signal content)
# ---------------------------------------------------------------------------

_CRYPTO_PENALTIES: list[tuple[str, re.Pattern[str], int]] = [
    # Price prediction spam (highest penalty)
    (
        "price_prediction",
        re.compile(
            r"\b(price\s+prediction|will\s+reach|will\s+hit|to\s+the\s+moon|"
            r"when\s+lambo|\d+x|100x|to\s+\$\d+k|target\s+price)\b",
            re.I,
        ),
        25,
    ),
    # Shilling/pumping spam
    (
        "shilling",
        re.compile(
            r"\b(buy\s+now|don't\s+miss|gem|moonshot|parabolic|"
            r"next\s+bitcoin|rocket|mooning|diamond\s+hands)\b",
            re.I,
        ),
        20,
    ),
    # Generic market wraps
    (
        "generic_wrap",
        re.compile(
            r"\b(crypto\s+market\s+update|daily\s+crypto\s+recap|"
            r"crypto\s+daily|market\s+wrap|today\s+in\s+crypto)\b",
            re.I,
        ),
        15,
    ),
    # NFT/Meta fluff (unless DeFi-related)
    (
        "nft_meta_fluff",
        re.compile(
            r"\b(nft\s+collection|metaverse\s+project|pfp\s+project|"
            r"nft\s+drop)\b",
            re.I,
        ),
        10,
    ),
]


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _text(candidate: ScoringCandidate) -> str:
    """Get combined text from title and snippet."""
    parts = [candidate.title]
    if candidate.snippet:
        parts.append(candidate.snippet)
    return " ".join(parts).lower()


def _has_crypto_context(text: str) -> bool:
    """Check if text has crypto-related context.

    Used to avoid false positives on ambiguous terms like "SEC"
    (could be traditional finance).
    """
    crypto_terms = [
        "bitcoin", "btc", "ethereum", "eth", "crypto", "cryptocurrency",
        "blockchain", "defi", "nft", "stablecoin", "binance", "coinbase",
        "solana", "sol", "cardano", "ada", "ripple", "xrp", "dogecoin",
        "doge", "polkadot", "dot", "avalanche", "avax", "polygon", "matic",
    ]
    text_lower = text.lower()
    return any(term in text_lower for term in crypto_terms)


# ---------------------------------------------------------------------------
# Post-adjustment function (v3 crypto-specific)
# ---------------------------------------------------------------------------


def _apply_crypto_post_adjustments(
    candidate: ScoringCandidate,
    base: ScoringResult,
) -> ScoringResult:
    """Apply v3 crypto-specific post-adjustments to a base score."""
    text = _text(candidate)
    has_crypto = _has_crypto_context(text)

    original_score = base.impact_score
    adj = 0

    # Apply crypto domain tier score (replaces base tier)
    crypto_tier_score = _get_crypto_domain_tier_score(candidate.source_domain)
    # Calculate adjustment from base tier (assume base was 5)
    tier_adj = crypto_tier_score - 5
    adj += tier_adj
    base.flags.append(f"v3_tier:{crypto_tier_score}")

    # Detect crypto topic
    topic = _detect_crypto_topic(text)
    if topic:
        base.topic = topic
        base.flags.append(f"v3_topic:{topic}")

    # Apply protocol/exchange boosters
    for name, rx, boost in _CRYPTO_PROTOCOL_BOOSTERS:
        if rx.search(text):
            # Require crypto context for regulation-related terms
            if "regulatory" in name or "sec" in name.lower():
                if not has_crypto:
                    continue
            adj += boost
            base.flags.append(f"v3_boost:protocol:{name}")

    # Apply market structure boosters
    for name, rx, boost in _CRYPTO_MARKET_STRUCTURE_BOOSTERS:
        if rx.search(text):
            adj += boost
            base.flags.append(f"v3_boost:market:{name}")

    # Apply technical boosters
    for name, rx, boost in _CRYPTO_TECHNICAL_BOOSTERS:
        if rx.search(text):
            adj += boost
            base.flags.append(f"v3_boost:technical:{name}")

    # Breaking news bypass (boost regardless of domain)
    if re.search(r"\bbreaking\b", text, re.I):
        adj += _BREAKING_NEWS_BOOST
        base.flags.append("v3_boost:breaking_news")

    # Apply crypto-specific penalties
    for name, rx, penalty in _CRYPTO_PENALTIES:
        if rx.search(text):
            adj -= penalty
            base.flags.append(f"v3_penalty:{name}")

    # Preview/anticipation penalty (lighter than v2 since crypto moves fast)
    if re.search(r"\b(expected|ahead|likely|set\s+to)\b", text, re.I):
        # Check if it's just preview or has outcome
        has_outcome = re.search(
            r"\b(rose|fell|jumped|plunged|soared|surged|announced|approved|rejected)\b",
            text, re.I,
        )
        if not has_outcome:
            adj -= 8
            base.flags.append("v3_penalty:preview_only")

    # Apply score adjustments
    score = original_score + adj

    # Topic-based scoring boosts
    if topic == "protocol_risk":
        score = max(score, 55)  # Ensure protocol risk hits high band
    elif topic == "regulation":
        score = max(score, 50)  # Regulation gets strong floor
    elif topic in ("defi", "derivatives"):
        score = max(score, 42)  # Market structure gets medium floor

    # Soft cap to prevent any single category from dominating
    if score > 75:
        score = min(score, 72)

    # Clamp final score to 0..100
    base.impact_score = max(0, min(100, int(score)))

    # Tag v3
    base.scorer_version = "heuristic_v3"

    # Add brief reason for visibility
    delta = base.impact_score - original_score
    if delta != 0:
        base.reasons.append(f"v3_adjust:{delta:+d}")

    return base


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------


def score_candidates_v3(
    candidates: list[ScoringCandidate],
    config: ScoringConfig,
    recent_simhashes: Optional[list[int]] = None,
) -> list[ScoringResult]:
    """Score a batch of candidates using heuristic v3 (crypto-specific).

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
        r = _apply_crypto_post_adjustments(c, r)
        results.append(r)

    # Sort by impact score descending
    results.sort(key=lambda r: r.impact_score, reverse=True)
    return results
