#!/usr/bin/env python3
"""Deterministic evaluation framework for us_close (macro-heavy).

This module implements:
- A/B/C/D classifier for news items using title+snippet (+ optional feed domain/source_name)
- Evaluation metrics: TopK composition, policy inversions (A>B>C>D), spam/template constraints

Primary goal: lock the evaluation rubric/metrics BEFORE changing the scorer.

Input record format expected:
{
  "id": int,
  "title": str,
  "snippet": str,
  "impact_score": int,
  "source_name": str,
  "feed_url": str | None,
  ...
}
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
import os
import re
from urllib.parse import urlparse

import psycopg2
from dotenv import load_dotenv


def load_ranked_items_from_db(days: float = 1.0) -> list[dict[str, Any]]:
    """Load scored news items for a recent window (default: last 24h).

    Returns items sorted by impact_score desc.

    NOTE: We keep this literal/raw so the evaluation logic is identical to dataset mode.
    """

    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL not set in environment")

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    try:
        query = """
        SELECT
            ni.id,
            ni.source_name,
            ni.title,
            COALESCE(ni.snippet, '') AS snippet,
            ni.raw_metadata->>'feed_url' AS feed_url,
            ns.impact_score,
            ns.scorer_version,
            ni.ingested_at,
            ni.published_at
        FROM news_items ni
        JOIN news_scores ns ON ni.id = ns.news_item_id
        WHERE ni.ingested_at >= %s
        ORDER BY ns.impact_score DESC
        """
        cur.execute(query, (cutoff,))
        rows = cur.fetchall()
    finally:
        conn.close()

    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "id": row[0],
                "source_name": row[1],
                "title": row[2],
                "snippet": row[3],
                "feed_url": row[4],
                "impact_score": row[5],
                "scorer_version": row[6],
                "ingested_at": row[7].isoformat() if row[7] else None,
                "published_at": row[8].isoformat() if row[8] else None,
            }
        )

    return out


# -----------------------------
# Helpers
# -----------------------------


def _text(item: dict[str, Any]) -> str:
    title = (item.get("title") or "").strip()
    snippet = (item.get("snippet") or "").strip()
    return f"{title} {snippet}".strip().lower()


def _has_keyword(text: str, kw: str) -> bool:
    """Keyword match that avoids substring false positives for short tokens.

    Rules:
    - Multi-word keywords (contain whitespace) are matched as simple substrings.
    - Single-word short tokens (len<=4) are matched on word boundaries (\b).
    - Longer single words use substring match (keeps behavior for things like
      'inflation', 'unemployment', etc.).

    This specifically prevents cases like 'fed' matching inside 'federal'.
    """

    kw = kw.strip().lower()
    if not kw:
        return False

    if any(ch.isspace() for ch in kw):
        return kw in text

    if len(kw) <= 4:
        return re.search(rf"\\b{re.escape(kw)}\\b", text) is not None

    return kw in text


def _extract_domain(feed_url: str | None) -> str:
    if not feed_url:
        return ""
    try:
        domain = urlparse(feed_url).netloc.lower()
    except Exception:
        return ""
    if domain.startswith("www."):
        domain = domain[4:]
    if domain.startswith("feeds."):
        domain = domain[6:]
    return domain


# -----------------------------
# Pattern libraries
# -----------------------------

# D: clickbait/noise patterns (hard exclusion)
D_PATTERNS: list[tuple[str, str]] = [
    (
        "pundit_content",
        r"\b(jim\s+cramer|cramer\s+says|motley\s+fool|seeking\s+alpha|mad\s+money)\b",
    ),
    (
        "stock_picks",
        r"\b(stocks?\s+to\s+buy|top\s+\d+\s+stocks?|best\s+(dividend\s+)?stocks?|should\s+you\s+buy|hot\s+stocks?)\b",
    ),
    (
        "fomo_bait",
        r"\b(if\s+you('d|\s+had)\s+invested|millionaire[\s-]maker|could\s+(double|triple|10x)|get\s+rich|next\s+(amazon|apple|nvidia|tesla))\b",
    ),
    (
        "why_stock_moved",
        r"\bwhy\s+\w+\s+(stock\s+)?(crashed|soared|plunged|skyrocketed|fell|jumped)\b",
    ),
    (
        "listicle",
        r"\b(\d+\s+reasons?\s+why|\d+\s+best|\d+\s+worst|\d+\s+things?\s+to|top\s+\d+\s+reasons?)\b",
    ),
]
D_REGEX = [(name, re.compile(pat, re.IGNORECASE)) for name, pat in D_PATTERNS]

# Earnings routine markers (tend toward C unless systemic markers present)
EARNINGS_ROUTINE = re.compile(
    r"\b(beats?\s+estimates?|misses?\s+estimates?|tops?\s+expectations?|falls?\s+short|q\d\s+profit|q\d\s+earnings)\b",
    re.IGNORECASE,
)

# Systemic earnings markers (B; possibly A if explicitly systemic)
EARNINGS_SYSTEMIC = re.compile(
    r"\b(profit\s+warning|guidance\s+cut|guidance\s+lower|sector[-\s]wide|industry[-\s]wide|bellwether|mass\s+layoffs|restructuring|large\s+layoffs)\b",
    re.IGNORECASE,
)

# A: macro catalysts keywords
A_KEYWORDS: dict[str, list[str]] = {
    "central_bank": [
        "fed",
        "federal reserve",
        "fomc",
        "powell",
        "ecb",
        "boe",
        "boj",
        "rate cut",
        "rate hike",
        "interest rate",
        "qt",
        "qe",
    ],
    "macro_data": [
        "cpi",
        "pce",
        "inflation",
        "deflation",
        "gdp",
        "nfp",
        "nonfarm",
        "payrolls",
        "jobs report",
        "jobless claims",
        "ism",
        "pmi",
    ],
    "geopolitics_policy": [
        "tariff",
        "tariffs",
        "sanctions",
        "embargo",
        "trade war",
        "war",
        "conflict",
        "invasion",
    ],
    "energy_shock": ["opec", "opec+", "supply disruption", "pipeline", "shipping", "hormuz"],
    "credit_systemic": [
        "credit spread",
        "high yield",
        "default",
        "bank stress",
        "liquidity",
        "sovereign",
        "sovereign debt",
    ],
}

# B: digest markers
B_KEYWORDS: dict[str, list[str]] = {
    "market_wrap": [
        "stock market today",
        "markets",
        "shares",
        "stocks",
        "s&p",
        "dow",
        "nasdaq",
        "close",
        "rally",
        "selloff",
    ],
    "rates_fx": ["yield", "yields", "treasury", "treasuries", "dollar", "dxy", "fx", "forex"],
    "commodities": ["oil", "crude", "wti", "brent", "gold", "silver", "copper", "natural gas"],
}

# Templates/spam families
TEMPLATE_MARKET_TODAY = re.compile(r"\bstock\s+market\s+today\b", re.IGNORECASE)
TEMPLATE_PREMARKET_EARNINGS = re.compile(r"\bpre-?market\s+earnings\s+report\b", re.IGNORECASE)


# -----------------------------
# Classification
# -----------------------------


@dataclass(frozen=True)
class Classification:
    label: str  # A/B/C/D
    reasons: list[str]


def classify(item: dict[str, Any]) -> Classification:
    """Classify a news item into A/B/C/D for us_close macro-heavy."""

    t = _text(item)
    reasons: list[str] = []

    # 1) D overrides everything (hard exclusion)
    for name, rx in D_REGEX:
        if rx.search(t):
            reasons.append(f"D:{name}")
    if reasons:
        return Classification(label="D", reasons=reasons)

    # 2) Earnings special handling
    if EARNINGS_SYSTEMIC.search(t):
        return Classification(label="B", reasons=["B:systemic_earnings"])
    if EARNINGS_ROUTINE.search(t):
        return Classification(label="C", reasons=["C:routine_earnings"])

    # 3) A detection (macro catalysts)
    a_hits = 0
    a_reasons: list[str] = []
    for group, kws in A_KEYWORDS.items():
        if any(_has_keyword(t, kw) for kw in kws):
            a_hits += 1
            a_reasons.append(f"A:{group}")

    # Heuristic: require >=1 group hit, but elevate if >=2 groups
    if a_hits >= 2:
        return Classification(label="A", reasons=a_reasons)
    if a_hits == 1:
        # Some single-group hits are truly A (e.g., CPI/NFP/FOMC/OPEC). Treat as A.
        return Classification(label="A", reasons=a_reasons)

    # 4) B detection (digest)
    b_hits = 0
    b_reasons: list[str] = []
    for group, kws in B_KEYWORDS.items():
        if any(_has_keyword(t, kw) for kw in kws):
            b_hits += 1
            b_reasons.append(f"B:{group}")

    if b_hits >= 1:
        return Classification(label="B", reasons=b_reasons)

    # 5) Default to C
    return Classification(label="C", reasons=["C:default"])


# -----------------------------
# Evaluation metrics
# -----------------------------

_LABEL_ORDER = {"A": 3, "B": 2, "C": 1, "D": 0}


@dataclass(frozen=True)
class TopKComposition:
    k: int
    counts: dict[str, int]


@dataclass(frozen=True)
class InversionCounts:
    k: int
    hard_D_over_A_or_B: int
    D_in_top_k: int


@dataclass(frozen=True)
class SpamCounts:
    k: int
    market_wrap_templates: int
    premarket_earnings_templates: int


def _topk(items: list[dict[str, Any]], k: int) -> list[dict[str, Any]]:
    return items[: min(k, len(items))]


def compute_topk_composition(items_ranked: list[dict[str, Any]], k: int) -> TopKComposition:
    counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    for item in _topk(items_ranked, k):
        label = item["_class"]["label"]
        counts[label] += 1
    return TopKComposition(k=k, counts=counts)


def compute_inversions(items_ranked: list[dict[str, Any]], k: int) -> InversionCounts:
    top = _topk(items_ranked, k)
    d_in_top = sum(1 for it in top if it["_class"]["label"] == "D")

    # Hard inversion: any D ranked above any A or B in top-k window
    hard = 0
    # For each D at position i, check if any A/B occurs after it => D above A/B
    seen_good_after = [
        any(it2["_class"]["label"] in ("A", "B") for it2 in top[i + 1 :])
        for i, it in enumerate(top)
        if it["_class"]["label"] == "D"
    ]
    hard = sum(1 for x in seen_good_after if x)

    return InversionCounts(k=k, hard_D_over_A_or_B=hard, D_in_top_k=d_in_top)


def compute_spam(items_ranked: list[dict[str, Any]], k: int) -> SpamCounts:
    top = _topk(items_ranked, k)
    mw = 0
    pm = 0
    for it in top:
        t = _text(it)
        if TEMPLATE_MARKET_TODAY.search(t):
            mw += 1
        if TEMPLATE_PREMARKET_EARNINGS.search(t):
            pm += 1
    return SpamCounts(k=k, market_wrap_templates=mw, premarket_earnings_templates=pm)


@dataclass(frozen=True)
class EvalResult:
    top12: TopKComposition
    top20: TopKComposition
    top50: TopKComposition
    inversions20: InversionCounts
    inversions50: InversionCounts
    spam12: SpamCounts
    spam20: SpamCounts


def evaluate(items_ranked: list[dict[str, Any]]) -> EvalResult:
    """Evaluate a ranked list. Items must be pre-annotated with _class."""
    return EvalResult(
        top12=compute_topk_composition(items_ranked, 12),
        top20=compute_topk_composition(items_ranked, 20),
        top50=compute_topk_composition(items_ranked, 50),
        inversions20=compute_inversions(items_ranked, 20),
        inversions50=compute_inversions(items_ranked, 50),
        spam12=compute_spam(items_ranked, 12),
        spam20=compute_spam(items_ranked, 20),
    )


def assert_contract(res: EvalResult) -> list[str]:
    """Return list of contract violations (empty = pass)."""
    v: list[str] = []

    c12 = res.top12.counts
    if not (c12["A"] >= 6 and c12["B"] >= 4 and c12["C"] <= 2 and c12["D"] == 0):
        v.append(f"Top12 composition fail: {c12}")

    c20 = res.top20.counts
    if not (c20["A"] >= 8 and c20["C"] <= 5 and c20["D"] <= 1):
        v.append(f"Top20 composition fail: {c20}")

    c50 = res.top50.counts
    d_rate = c50["D"] / max(1, sum(c50.values()))
    if d_rate > 0.05:
        v.append(f"Top50 D-rate fail: D={c50['D']}/50 ({d_rate * 100:.1f}%)")

    if res.inversions50.hard_D_over_A_or_B > 0:
        v.append(
            f"Hard inversion fail (Top50): D above A/B count={res.inversions50.hard_D_over_A_or_B}"
        )

    # Spam constraints
    if res.spam12.market_wrap_templates > 1:
        v.append(f"Spam fail (Top12): market_wrap_templates={res.spam12.market_wrap_templates} > 1")

    return v


def annotate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return new list annotated with _class and domain."""
    out: list[dict[str, Any]] = []
    for it in items:
        c = classify(it)
        it2 = dict(it)
        it2["_domain"] = _extract_domain(it.get("feed_url"))
        it2["_class"] = {"label": c.label, "reasons": c.reasons}
        out.append(it2)
    return out
