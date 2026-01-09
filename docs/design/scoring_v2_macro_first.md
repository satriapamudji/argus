# Scoring v2: Macro-First Design Document

**Author:** Argus Team  
**Status:** Draft  
**Created:** 2026-01-09  
**Last Updated:** 2026-01-09

---

## 1. Executive Summary

### Problem Statement

The current scoring system (`heuristic_v1`) fails to reliably surface macro-relevant news for daily market updates. Three critical deficiencies undermine the curation quality:

1. **Broken Source Tier Signal**: The `source_name` field contains RSS feed titles (e.g., "Markets", "Earnings") rather than publisher identity (e.g., "Reuters", "CNBC"). This causes ~80% of items to fall through to the 5-point default tier, eliminating source authority as a ranking signal.

2. **No Penalty System**: Clickbait content ("5 stocks to buy now", "Jim Cramer says", "if you'd invested $1000") scores equivalently to genuine macro news. Low-quality content pollutes top-K selection.

3. **Score Compression**: Most items cluster in the 40-55 range instead of utilizing the full 0-100 scale. This makes ranking unstable and selection arbitrary.

### Solution Overview

Scoring v2 ("Macro-First") introduces:

- **Domain-based source tier resolution** using `feed_url` instead of `source_name`
- **Macro-first category buckets** replacing flat keyword scoring with hierarchical topic importance
- **Penalty system** for clickbait patterns with configurable negative weights
- **Expanded score range** through additive bucket scoring and penalties

The result is a wider score distribution where macro-critical news (Fed, CPI, geopolitics) consistently ranks above single-stock noise.

---

## 2. Goals & Non-Goals

### Goals

1. **Fix source tier resolution**: Use feed URL domain to accurately identify publisher authority
2. **Prioritize macro news**: Fed/FOMC, inflation, rates, and geopolitical events should rank highest
3. **Penalize clickbait**: Reduce scores for stock picks, price targets, and pundit content
4. **Widen score distribution**: Achieve meaningful separation between tiers (target: 20+ point spread between macro and noise)
5. **Provide evaluation tooling**: CLI command to audit scoring quality against policy

### Non-Goals

- **Machine learning scoring**: v2 remains rule-based; ML is deferred to v3
- **Real-time scoring adjustments**: No feedback loop from user engagement
- **Cross-stream scoring differences**: Same scoring logic applies to all streams
- **Historical re-scoring**: Existing scores remain unchanged; v2 applies to new items only
- **Source tier auto-discovery**: Domain tiers remain manually configured

---

## 3. Background

### Current State Analysis

#### Source Tier Problem

The current `SourceTiersConfig` matches against `source_name`:

```python
# config.py lines 119-121
tier_1: list[str] = field(default_factory=lambda: ["Reuters", "Bloomberg", "WSJ"])
tier_2: list[str] = field(default_factory=lambda: ["CNBC", "Financial Times"])
tier_3: list[str] = field(default_factory=lambda: ["Yahoo Finance", "MarketWatch"])
```

However, `source_name` is extracted from RSS feed titles in `rss_parser.py:41-70`:

```python
def extract_source_name(feed: dict[str, Any], feed_url: str) -> str:
    feed_info = feed.get("feed", {})
    raw_title = feed_info.get("title", "")
    # Returns "Markets", "Earnings", etc. - NOT "CNBC", "Nasdaq"
```

**Concrete examples of the problem:**

| Feed URL | Actual source_name | Expected | Tier Match |
|----------|-------------------|----------|------------|
| `cnbc.com/id/100003114/...` | "Markets" | "CNBC" | Falls to 5 pts |
| `cnbc.com/id/100727362/...` | "Finance" | "CNBC" | Falls to 5 pts |
| `nasdaq.com/.../Markets` | "Markets" | "Nasdaq" | Falls to 5 pts |

The `feed_url` is already stored in `raw_metadata` during ingestion (`rss_parser.py:180-184`) but is not accessible during scoring.

#### No Penalty System

The current scorer (`heuristics.py`) only adds points, never subtracts:

```python
# Current components are all additive
breakdown = ScoreBreakdown(
    recency=recency_score,        # 0-25
    source_tier=source_score,     # 0-20
    keyword_relevance=keyword_score,  # 0-30
    uniqueness=uniqueness_score,  # 0-15
    breaking_urgency=breaking_score,  # 0-10
)
```

This means clickbait like "5 Best Dividend Stocks for 2026" can score 50+ points if it contains macro keywords and is recent.

#### Score Compression

With max theoretical score of 100 and most items hitting:
- Recency: 15-25 (most items are recent)
- Source: 5 (tier fallback)
- Keywords: 10-20 (many market terms match)
- Uniqueness: 8 (default when no comparison)
- Breaking: 0

Typical range: **38-58 points** - only 20 points of effective discrimination.

### Impact on Curation

When preparing facts bundles for generation, items are selected by `impact_score` descending. With compressed scores:

1. Macro-critical news ("Fed signals pause") may rank below clickbait ("3 stocks to buy")
2. Top-K selection becomes arbitrary due to score ties
3. Generated market updates may lead with irrelevant content

---

## 4. Detailed Design

### 4.1 Data Model Changes

#### ScoringCandidate

Add `feed_url` field to provide domain extraction capability:

```python
# src/argus/scoring/types.py

@dataclass
class ScoringCandidate:
    """A news item candidate for scoring."""
    
    news_item_id: int
    fingerprint_id: int
    source_name: str
    source_url: str
    title: str
    snippet: Optional[str]
    published_at: Optional[datetime]
    ingested_at: datetime
    simhash: Optional[int] = None
    feed_url: Optional[str] = None  # NEW: For domain-based tier resolution
    
    @property
    def text_for_scoring(self) -> str:
        """Combined text for keyword/topic analysis."""
        parts = [self.title]
        if self.snippet:
            parts.append(self.snippet)
        return " ".join(parts)
    
    @property
    def source_domain(self) -> Optional[str]:
        """Extract normalized domain from feed_url for tier matching."""
        if not self.feed_url:
            return None
        return extract_source_domain(self.feed_url)
```

#### ScoreBreakdown

Replace `keyword_relevance` with category buckets and add penalty field:

```python
# src/argus/scoring/types.py

@dataclass
class ScoreBreakdown:
    """Breakdown of individual scoring components."""
    
    # Preserved from v1
    recency: int = 0           # 0-25 pts
    source_tier: int = 0       # 0-20 pts
    uniqueness: int = 0        # 0-15 pts
    breaking_urgency: int = 0  # 0-10 pts
    
    # NEW: Category buckets (replace keyword_relevance)
    macro_catalyst: int = 0    # 0-15 pts
    rates_credit: int = 0      # 0-10 pts
    commodities: int = 0       # 0-8 pts
    geopolitics: int = 0       # 0-10 pts
    systemic_earnings: int = 0 # 0-8 pts
    
    # NEW: Penalty (negative)
    penalty: int = 0           # -25 to 0 pts
    
    @property
    def total(self) -> int:
        """Total heuristic score (0-100, clamped)."""
        raw = (
            self.recency
            + self.source_tier
            + self.uniqueness
            + self.breaking_urgency
            + self.macro_catalyst
            + self.rates_credit
            + self.commodities
            + self.geopolitics
            + self.systemic_earnings
            + self.penalty  # Negative value
        )
        return max(0, min(100, raw))
    
    def to_reasons(self) -> list[str]:
        """Convert breakdown to human-readable reasons list."""
        reasons = []
        if self.recency > 0:
            reasons.append(f"recency: +{self.recency}")
        if self.source_tier > 0:
            reasons.append(f"source_tier: +{self.source_tier}")
        if self.macro_catalyst > 0:
            reasons.append(f"macro_catalyst: +{self.macro_catalyst}")
        if self.rates_credit > 0:
            reasons.append(f"rates_credit: +{self.rates_credit}")
        if self.commodities > 0:
            reasons.append(f"commodities: +{self.commodities}")
        if self.geopolitics > 0:
            reasons.append(f"geopolitics: +{self.geopolitics}")
        if self.systemic_earnings > 0:
            reasons.append(f"systemic_earnings: +{self.systemic_earnings}")
        if self.uniqueness > 0:
            reasons.append(f"uniqueness: +{self.uniqueness}")
        if self.breaking_urgency > 0:
            reasons.append(f"breaking: +{self.breaking_urgency}")
        if self.penalty < 0:
            reasons.append(f"penalty: {self.penalty}")
        return reasons
```

#### ScoringResult

Update `scorer_version` default:

```python
scorer_version: str = "heuristic_v2"
```

### 4.2 Domain-Based Source Tier Mapping

#### Domain Extraction Logic

```python
# src/argus/scoring/domain_tiers.py

from urllib.parse import urlparse

def extract_source_domain(feed_url: str) -> str:
    """Extract normalized domain from feed URL for tier matching.
    
    Args:
        feed_url: Full RSS feed URL.
        
    Returns:
        Lowercase domain without 'www.' prefix.
        
    Examples:
        >>> extract_source_domain("https://www.cnbc.com/id/100003114/device/rss/rss.html")
        "cnbc.com"
        >>> extract_source_domain("https://feeds.reuters.com/markets/news")
        "reuters.com"
    """
    if not feed_url:
        return ""
    
    try:
        parsed = urlparse(feed_url)
        domain = parsed.netloc.lower()
        
        # Strip www. prefix
        if domain.startswith("www."):
            domain = domain[4:]
        
        # Handle feeds.* subdomains (e.g., feeds.reuters.com -> reuters.com)
        if domain.startswith("feeds."):
            domain = domain[6:]
        
        return domain
    except Exception:
        return ""
```

#### Domain Tier Configuration

```python
# src/argus/config.py

@dataclass
class DomainTiersConfig:
    """Domain-based source tier configuration for scoring v2.
    
    Uses feed URL domain instead of source_name for tier matching.
    
    tier_1: Wire services, premier financial news (20 pts)
    tier_2: Major financial media (15 pts)
    tier_3: General financial coverage (10 pts)
    Unlisted domains default to 5 pts.
    """
    
    tier_1: list[str] = field(default_factory=lambda: [
        "reuters.com",
        "bloomberg.com", 
        "wsj.com",
        "ft.com",
    ])
    tier_2: list[str] = field(default_factory=lambda: [
        "cnbc.com",
        "marketwatch.com",
        "barrons.com",
    ])
    tier_3: list[str] = field(default_factory=lambda: [
        "yahoo.com",
        "nasdaq.com",
        "investing.com",
    ])
    
    def get_tier_score(self, domain: str) -> int:
        """Get score for a domain based on its tier.
        
        Args:
            domain: Normalized domain (lowercase, no www.).
            
        Returns:
            Score: 20 for tier_1, 15 for tier_2, 10 for tier_3, 5 for unlisted.
        """
        domain_lower = domain.lower()
        
        # Exact match for tier 1
        if domain_lower in [d.lower() for d in self.tier_1]:
            return 20
        
        # Exact match for tier 2
        if domain_lower in [d.lower() for d in self.tier_2]:
            return 15
        
        # Exact match for tier 3
        if domain_lower in [d.lower() for d in self.tier_3]:
            return 10
        
        # Unlisted
        return 5
```

#### Tier Resolution in Scorer

```python
# src/argus/scoring/heuristics.py

def _score_source_tier(self, candidate: ScoringCandidate) -> int:
    """Score based on source tier (0-20 pts).
    
    Uses domain-based matching via feed_url (v2) with fallback
    to source_name matching (v1 compatibility during transition).
    """
    # v2: Try domain-based matching first
    if candidate.feed_url:
        domain = extract_source_domain(candidate.feed_url)
        if domain:
            return self.domain_tiers.get_tier_score(domain)
    
    # Fallback: unlisted default
    return 5
```

### 4.3 Macro-First Category Buckets

Category buckets replace the flat `keyword_relevance` scoring with hierarchical topic importance. Each bucket has specific keywords and a score cap.

#### Bucket Definitions

```python
# src/argus/scoring/macro_buckets.py

from dataclasses import dataclass
from typing import Optional
import re

@dataclass
class CategoryBucket:
    """A scoring category with keywords and point cap."""
    name: str
    keywords: list[str]
    max_points: int
    points_per_match: int = 3  # Default points per keyword match

# Bucket configurations
MACRO_CATALYST = CategoryBucket(
    name="macro_catalyst",
    keywords=[
        "fed", "federal reserve", "fomc", "powell",
        "cpi", "pce", "inflation", "deflation",
        "gdp", "nfp", "nonfarm", "payrolls", "jobs report",
        "rate hike", "rate cut", "interest rate",
        "quantitative tightening", "qt", "quantitative easing", "qe",
        "recession", "soft landing", "hard landing",
    ],
    max_points=15,
    points_per_match=5,
)

RATES_CREDIT = CategoryBucket(
    name="rates_credit", 
    keywords=[
        "yield", "yields", "treasury", "treasuries",
        "bond", "bonds", "credit spread", "high yield",
        "default", "sovereign", "sovereign debt",
        "dollar", "dxy", "fx", "forex", "currency",
        "inverted yield curve", "yield curve",
    ],
    max_points=10,
    points_per_match=3,
)

COMMODITIES = CategoryBucket(
    name="commodities",
    keywords=[
        "oil", "crude", "wti", "brent",
        "gold", "silver", "copper", "metals",
        "opec", "opec+", "lng", "natural gas",
        "commodity", "commodities",
    ],
    max_points=8,
    points_per_match=3,
)

GEOPOLITICS = CategoryBucket(
    name="geopolitics",
    keywords=[
        "tariff", "tariffs", "trade war",
        "sanctions", "sanction", "embargo",
        "war", "conflict", "military",
        "election", "elections", "vote",
        "china", "russia", "ukraine", "taiwan", "iran",
        "geopolitical", "geopolitics",
    ],
    max_points=10,
    points_per_match=4,
)

SYSTEMIC_EARNINGS = CategoryBucket(
    name="systemic_earnings",
    keywords=[
        "profit warning", "guidance cut", "guidance lower",
        "major miss", "significant miss", "disappointing",
        "bellwether", "sector-wide", "industry-wide",
        "layoffs", "mass layoffs", "restructuring",
    ],
    max_points=8,
    points_per_match=4,
)

ALL_BUCKETS = [
    MACRO_CATALYST,
    RATES_CREDIT, 
    COMMODITIES,
    GEOPOLITICS,
    SYSTEMIC_EARNINGS,
]


def score_bucket(text: str, bucket: CategoryBucket) -> int:
    """Score text against a category bucket.
    
    Args:
        text: Lowercase text to analyze.
        bucket: Category bucket configuration.
        
    Returns:
        Score capped at bucket.max_points.
    """
    text_lower = text.lower()
    matches = sum(1 for kw in bucket.keywords if kw in text_lower)
    raw_score = matches * bucket.points_per_match
    return min(raw_score, bucket.max_points)


def score_all_buckets(text: str) -> dict[str, int]:
    """Score text against all category buckets.
    
    Args:
        text: Combined title + snippet text.
        
    Returns:
        Dict mapping bucket name to score.
    """
    text_lower = text.lower()
    return {
        bucket.name: score_bucket(text_lower, bucket)
        for bucket in ALL_BUCKETS
    }
```

### 4.4 Penalty System

#### Penalty Pattern Categories

```python
# src/argus/scoring/penalties.py

import re
from dataclasses import dataclass
from typing import Pattern

@dataclass
class PenaltyPattern:
    """A regex pattern with associated penalty points."""
    name: str
    pattern: Pattern
    penalty: int  # Negative value

# Penalty definitions
PENALTY_PATTERNS: list[PenaltyPattern] = [
    # Stock picking / investment advice (-15)
    PenaltyPattern(
        name="stock_picks",
        pattern=re.compile(
            r"\b(stocks?\s+to\s+buy|"
            r"top\s+\d+\s+stocks?|"
            r"best\s+(dividend\s+)?stocks?|"
            r"should\s+you\s+buy|"
            r"buy\s+the\s+dip|"
            r"hot\s+stocks?)\b",
            re.IGNORECASE
        ),
        penalty=-15,
    ),
    
    # Price targets / analyst ratings (-10)
    PenaltyPattern(
        name="price_targets",
        pattern=re.compile(
            r"\b(price\s+target|"
            r"analyst\s+(upgrades?|downgrades?|rating)|"
            r"(raises?|lowers?|cuts?)\s+price\s+target|"
            r"(buy|sell|hold)\s+rating)\b",
            re.IGNORECASE
        ),
        penalty=-10,
    ),
    
    # Insider trading noise (-8)
    PenaltyPattern(
        name="insider_activity",
        pattern=re.compile(
            r"\b(insider\s+(sold|bought|selling|buying)|"
            r"ceo\s+(sold|bought)|"
            r"executives?\s+(sold|bought))\b",
            re.IGNORECASE
        ),
        penalty=-8,
    ),
    
    # Pundit / personality content (-12)
    PenaltyPattern(
        name="pundit_content",
        pattern=re.compile(
            r"\b(jim\s+cramer|"
            r"cramer\s+says|"
            r"motley\s+fool|"
            r"seeking\s+alpha|"
            r"mad\s+money)\b",
            re.IGNORECASE
        ),
        penalty=-12,
    ),
    
    # Hypothetical returns / FOMO bait (-15)
    PenaltyPattern(
        name="fomo_bait",
        pattern=re.compile(
            r"\b(if\s+you('d|.had)\s+invested|"
            r"millionaire[\s-]maker|"
            r"could\s+(double|triple|10x)|"
            r"next\s+(amazon|apple|nvidia|tesla)|"
            r"life[\s-]changing\s+returns?|"
            r"get\s+rich)\b",
            re.IGNORECASE
        ),
        penalty=-15,
    ),
    
    # Sensationalist crash/soar language (-8)
    PenaltyPattern(
        name="sensationalist",
        pattern=re.compile(
            r"\b(why\s+\w+\s+(stock\s+)?(crashed|soared|plunged|skyrocketed)|"
            r"stock\s+(crashes|soars|plunges|skyrockets)|"
            r"is\s+(crashing|soaring))\b",
            re.IGNORECASE
        ),
        penalty=-8,
    ),
    
    # Earnings beat/miss noise (-5, moderate)
    PenaltyPattern(
        name="earnings_noise",
        pattern=re.compile(
            r"\b(beats?\s+estimates?|"
            r"misses?\s+estimates?|"
            r"tops?\s+expectations?|"
            r"falls?\s+short)\b",
            re.IGNORECASE
        ),
        penalty=-5,
    ),
    
    # Listicle patterns (-10)
    PenaltyPattern(
        name="listicle",
        pattern=re.compile(
            r"\b(\d+\s+reasons?\s+why|"
            r"\d+\s+best|"
            r"\d+\s+worst|"
            r"\d+\s+things?\s+to|"
            r"top\s+\d+\s+reasons?)\b",
            re.IGNORECASE
        ),
        penalty=-10,
    ),
    
    # Crypto spam (-8)
    PenaltyPattern(
        name="crypto_spam",
        pattern=re.compile(
            r"\b(meme\s+coin|"
            r"shiba|dogecoin|doge|"
            r"to\s+the\s+moon|"
            r"crypto\s+millionaire|"
            r"next\s+big\s+crypto)\b",
            re.IGNORECASE
        ),
        penalty=-8,
    ),
]


def calculate_penalty(text: str) -> tuple[int, list[str]]:
    """Calculate total penalty and matched patterns.
    
    Args:
        text: Combined title + snippet text.
        
    Returns:
        Tuple of (total_penalty, list of matched pattern names).
        Total penalty is capped at -25.
    """
    text_check = text.lower() if text else ""
    total_penalty = 0
    matched_patterns = []
    
    for pp in PENALTY_PATTERNS:
        if pp.pattern.search(text_check):
            total_penalty += pp.penalty
            matched_patterns.append(pp.name)
    
    # Cap total penalty at -25
    total_penalty = max(-25, total_penalty)
    
    return total_penalty, matched_patterns
```

### 4.5 Score Calculation

#### Formula

```
raw_score = (
    recency           # 0-25
    + source_tier     # 0-20
    + macro_catalyst  # 0-15
    + rates_credit    # 0-10
    + commodities     # 0-8
    + geopolitics     # 0-10
    + systemic_earnings # 0-8
    + uniqueness      # 0-15
    + breaking_urgency # 0-10
    + penalty         # -25 to 0
)

# Max theoretical: 121 (before penalty)
# With penalty: range -25 to 121
# After clamping: 0 to 100
impact_score = max(0, min(100, raw_score))
```

#### Component Ranges

| Component | Min | Max | Description |
|-----------|-----|-----|-------------|
| recency | 0 | 25 | Exponential decay over 24h (unchanged from v1) |
| source_tier | 0 | 20 | Domain-based: 20/15/10/5 |
| macro_catalyst | 0 | 15 | Fed, inflation, GDP, jobs |
| rates_credit | 0 | 10 | Yields, bonds, FX, credit |
| commodities | 0 | 8 | Oil, gold, metals |
| geopolitics | 0 | 10 | Tariffs, sanctions, conflict |
| systemic_earnings | 0 | 8 | Sector-wide earnings impact |
| uniqueness | 0 | 15 | SimHash distance (unchanged) |
| breaking_urgency | 0 | 10 | Breaking indicators (unchanged) |
| penalty | -25 | 0 | Clickbait pattern matches |

**Maximum theoretical:** 121 points (capped to 100)  
**Minimum possible:** -25 points (floored to 0)

#### Expected Score Distribution

| Content Type | Expected Range | Example |
|--------------|---------------|---------|
| Breaking macro (Fed) | 80-100 | "Fed signals rate cut in Q2" |
| Major geopolitical | 70-90 | "US announces new China tariffs" |
| Macro data release | 65-85 | "CPI comes in above expectations" |
| Quality market news | 50-70 | "S&P 500 closes at record high" |
| Standard earnings | 40-60 | "Apple reports Q4 earnings" |
| Minor market news | 30-50 | "Tech stocks edge higher" |
| Penalized content | 10-35 | "5 stocks to buy now" |
| Pure clickbait | 0-20 | "Jim Cramer's top stock picks" |

### 4.6 CLI Evaluation Command

#### Command Specification

```
argus score evaluate [OPTIONS]

Evaluate scoring quality by checking for policy violations in top-K results.

Options:
  --stream TEXT           Stream name (required for multi-stream configs)
  --window-hours INTEGER  Look back window [default: 24]
  --top-k INTEGER         Check top K items [default: 20]
  --verbose               Show individual violations
  --help                  Show this message and exit

Output:
  Summary statistics and optional violation details.
```

#### Implementation

```python
# src/argus/cli.py (new command)

@cli.group()
def score() -> None:
    """Scoring commands."""
    pass


@score.command()
@click.option("--stream", default=None, help="Stream name")
@click.option("--window-hours", default=24, help="Look back window (default: 24)")
@click.option("--top-k", default=20, help="Check top K items (default: 20)")
@click.option("--verbose", is_flag=True, help="Show individual violations")
@click.pass_context
def evaluate(
    ctx: click.Context,
    stream: Optional[str],
    window_hours: int,
    top_k: int,
    verbose: bool,
) -> None:
    """Evaluate scoring quality against policy.
    
    Checks top-K scored items for policy violations:
    - Clickbait patterns in high-ranking items
    - Missing macro catalysts in top positions
    - Source tier distribution anomalies
    
    Examples:
        argus score evaluate
        argus score evaluate --top-k 50 --verbose
        argus score evaluate --window-hours 48
    """
    from argus.db.connection import get_connection
    from argus.scoring.evaluate import run_evaluation
    
    config_path = ctx.obj.get("config_path")
    config = ArgusConfig.load(config_path)
    
    # Stream selection logic
    if stream is None:
        if len(config.streams) > 1:
            click.echo(
                "Error: --stream is required for multi-stream configs. "
                f"Available: {', '.join(config.list_streams())}",
                err=True,
            )
            raise SystemExit(2)
        stream = config.stream.name
    
    try:
        config.select_stream(stream)
    except UnknownStreamError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(2)
    
    try:
        conn = get_connection()
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
    
    click.echo(f"Evaluating top-{top_k} items (window: {window_hours}h)...")
    click.echo()
    
    result = run_evaluation(
        conn=conn,
        window_hours=window_hours,
        top_k=top_k,
    )
    conn.close()
    
    # Display results
    click.echo("=== Scoring Evaluation ===")
    click.echo()
    click.echo(f"Total items in window: {result.total_items}")
    click.echo(f"Items evaluated (top-{top_k}): {result.items_evaluated}")
    click.echo()
    click.echo("Policy Violations:")
    click.echo(f"  Clickbait in top-K: {result.clickbait_count}")
    click.echo(f"  Violation rate: {result.violation_rate:.1f}%")
    click.echo()
    click.echo("Macro Catalyst Check:")
    click.echo(f"  Macro items in top-10: {result.macro_in_top_10}")
    click.echo(f"  Macro presence: {'OK' if result.macro_in_top_10 > 0 else 'MISSING'}")
    click.echo()
    click.echo("Source Tier Distribution (top-K):")
    click.echo(f"  Tier 1 (20 pts): {result.tier_distribution.get(20, 0)}")
    click.echo(f"  Tier 2 (15 pts): {result.tier_distribution.get(15, 0)}")
    click.echo(f"  Tier 3 (10 pts): {result.tier_distribution.get(10, 0)}")
    click.echo(f"  Unlisted (5 pts): {result.tier_distribution.get(5, 0)}")
    
    if verbose and result.violations:
        click.echo()
        click.echo("--- Violations Detail ---")
        for v in result.violations:
            click.echo(f"  [{v.rank}] Score={v.score} | {v.title[:50]}...")
            click.echo(f"       Patterns: {', '.join(v.matched_patterns)}")
    
    # Exit code based on violation rate
    if result.violation_rate > 25.0:
        click.echo()
        click.echo(click.style("FAIL: Violation rate exceeds 25%", fg="red"))
        raise SystemExit(1)
    elif result.violation_rate > 10.0:
        click.echo()
        click.echo(click.style("WARN: Violation rate exceeds 10%", fg="yellow"))
```

#### Evaluation Logic

```python
# src/argus/scoring/evaluate.py

from dataclasses import dataclass, field
from argus.scoring.penalties import PENALTY_PATTERNS

@dataclass
class Violation:
    """A policy violation found in top-K."""
    rank: int
    news_item_id: int
    title: str
    score: int
    matched_patterns: list[str]

@dataclass
class EvaluationResult:
    """Result of scoring evaluation."""
    total_items: int
    items_evaluated: int
    clickbait_count: int
    violation_rate: float
    macro_in_top_10: int
    tier_distribution: dict[int, int]
    violations: list[Violation] = field(default_factory=list)


def run_evaluation(
    conn,
    window_hours: int,
    top_k: int,
) -> EvaluationResult:
    """Run scoring policy evaluation.
    
    Args:
        conn: Database connection.
        window_hours: Look-back window.
        top_k: Number of top items to evaluate.
        
    Returns:
        EvaluationResult with statistics and violations.
    """
    from argus.db.repository import get_scored_items_for_evaluation
    from argus.scoring.penalties import calculate_penalty
    from argus.scoring.macro_buckets import MACRO_CATALYST, score_bucket
    
    # Fetch scored items
    items = get_scored_items_for_evaluation(
        conn,
        window_hours=window_hours,
        limit=top_k,
    )
    
    total_items = len(items)
    violations = []
    macro_count_top_10 = 0
    tier_counts: dict[int, int] = {20: 0, 15: 0, 10: 0, 5: 0}
    
    for rank, item in enumerate(items, 1):
        # Check for penalty patterns
        text = f"{item.title} {item.snippet or ''}"
        penalty, matched = calculate_penalty(text)
        
        if penalty < 0:
            violations.append(Violation(
                rank=rank,
                news_item_id=item.news_item_id,
                title=item.title,
                score=item.impact_score,
                matched_patterns=matched,
            ))
        
        # Check macro presence in top 10
        if rank <= 10:
            bucket_score = score_bucket(text, MACRO_CATALYST)
            if bucket_score > 0:
                macro_count_top_10 += 1
        
        # Track tier distribution
        tier_score = item.source_tier_score  # Assumes this is in the result
        if tier_score in tier_counts:
            tier_counts[tier_score] += 1
    
    violation_rate = (len(violations) / total_items * 100) if total_items > 0 else 0.0
    
    return EvaluationResult(
        total_items=total_items,
        items_evaluated=min(top_k, total_items),
        clickbait_count=len(violations),
        violation_rate=violation_rate,
        macro_in_top_10=macro_count_top_10,
        tier_distribution=tier_counts,
        violations=violations,
    )
```

---

## 5. Configuration Changes

### New config.yaml Format

```yaml
scoring:
  enabled: true
  window_hours: 24
  max_items_per_run: 100
  scorer_version: "heuristic_v2"  # Changed from heuristic_v1
  
  # NEW: Domain-based source tiers (replaces name-based)
  domain_tiers:
    tier_1:  # 20 pts - Wire services, premier financial news
      - "reuters.com"
      - "bloomberg.com"
      - "wsj.com"
      - "ft.com"
    tier_2:  # 15 pts - Major financial media
      - "cnbc.com"
      - "marketwatch.com"
      - "barrons.com"
    tier_3:  # 10 pts - General financial coverage
      - "yahoo.com"
      - "nasdaq.com"
      - "investing.com"
    # Unlisted domains: 5 pts
  
  # DEPRECATED: source_tiers (name-based) - will be ignored in v2
  # source_tiers:
  #   tier_1: ["Reuters", "Bloomberg", "WSJ"]
  #   ...
  
  # LLM triage settings (unchanged)
  llm_triage_enabled: false
  llm_model: "mistralai/mistral-7b-instruct"
  llm_max_items: 25
```

### Configuration Loading Changes

```python
# src/argus/config.py

@dataclass
class ScoringConfig:
    """Scoring configuration."""
    
    enabled: bool = True
    window_hours: int = 24
    max_items_per_run: int = 100
    scorer_version: str = "heuristic_v2"  # Updated default
    
    # v2: Domain-based tiers
    domain_tiers: DomainTiersConfig = field(default_factory=DomainTiersConfig)
    
    # v1: Name-based tiers (deprecated, kept for error messages)
    source_tiers: SourceTiersConfig = field(default_factory=SourceTiersConfig)
    
    llm_triage_enabled: bool = False
    llm_model: str = "mistralai/mistral-7b-instruct"
    llm_max_items: int = 25
```

---

## 6. Migration Plan

### Rollout Strategy: In-Place Replacement

v2 replaces v1 directly with no side-by-side operation:

1. **Schema Update**: Add `feed_url` column resolution to scoring candidate queries
2. **Code Deploy**: Replace `heuristic_v1` scorer with `heuristic_v2`
3. **Config Update**: Add `domain_tiers` to config.yaml
4. **Verification**: Run `argus score evaluate` to confirm improvement

### Step-by-Step Migration

#### Step 1: Update ScoringCandidate Query

Modify the repository function that builds `ScoringCandidate` to include `feed_url` from `raw_metadata`:

```python
# src/argus/db/repository.py

def get_candidates_for_scoring(...) -> list[ScoringCandidate]:
    # ... existing query ...
    # Add: raw_metadata->>'feed_url' AS feed_url
```

#### Step 2: Deploy New Scoring Code

1. Add new files:
   - `src/argus/scoring/domain_tiers.py`
   - `src/argus/scoring/macro_buckets.py`
   - `src/argus/scoring/penalties.py`
   - `src/argus/scoring/evaluate.py`

2. Update existing files:
   - `src/argus/scoring/types.py` - New `ScoreBreakdown` fields
   - `src/argus/scoring/heuristics.py` - New scorer implementation
   - `src/argus/config.py` - Add `DomainTiersConfig`
   - `src/argus/cli.py` - Add `score evaluate` command

#### Step 3: Update Configuration

```yaml
# config.yaml - add domain_tiers section
scoring:
  scorer_version: "heuristic_v2"
  domain_tiers:
    tier_1:
      - "reuters.com"
      - "bloomberg.com"
      - "wsj.com"
      - "ft.com"
    tier_2:
      - "cnbc.com"
      - "marketwatch.com"
      - "barrons.com"
    tier_3:
      - "yahoo.com"
      - "nasdaq.com"
      - "investing.com"
```

#### Step 4: Verify with Evaluation

```bash
# Run evaluation after some items are scored with v2
argus score evaluate --verbose

# Expected output:
# Violation rate: <10%
# Macro presence: OK
# Tier distribution shows proper resolution (not all 5 pts)
```

### Rollback Plan

If issues are discovered:

1. Revert `scorer_version` to `"heuristic_v1"` in config.yaml
2. Redeploy previous code version
3. New items will score with v1; existing v2 scores remain in DB

---

## 7. Acceptance Criteria

### Functional Criteria

| ID | Criterion | Verification |
|----|-----------|--------------|
| AC-1 | Source tier correctly resolves for all configured feeds | Unit test: `cnbc.com` feed -> 15 pts, `nasdaq.com` -> 10 pts |
| AC-2 | Macro catalyst news scores 15+ points in category bucket | Unit test: "Fed cuts rates" -> macro_catalyst >= 10 |
| AC-3 | Clickbait patterns receive negative penalty | Unit test: "5 stocks to buy" -> penalty <= -10 |
| AC-4 | Score range spans 0-100 with meaningful distribution | Integration test: std dev > 15 across 100 items |
| AC-5 | CLI evaluate command runs without error | CLI test: `argus score evaluate --dry-run` exits 0 |
| AC-6 | Violation rate in top-20 < 25% | Evaluation test on production data |

### Performance Criteria

| ID | Criterion | Verification |
|----|-----------|--------------|
| PC-1 | Scoring 100 items completes in < 5 seconds | Benchmark test |
| PC-2 | No additional database queries per item | Code review: single query for candidates |
| PC-3 | Regex penalty matching < 1ms per item | Benchmark test |

### Quality Gates

- [ ] All existing scoring tests pass (with updated expectations)
- [ ] New unit tests for domain extraction, buckets, penalties
- [ ] Integration test showing score distribution improvement
- [ ] `argus score evaluate` shows < 25% violation rate

---

## 8. Test Plan

### Unit Tests

#### Domain Extraction (`test_domain_tiers.py`)

```python
def test_extract_source_domain_cnbc():
    url = "https://www.cnbc.com/id/100003114/device/rss/rss.html"
    assert extract_source_domain(url) == "cnbc.com"

def test_extract_source_domain_feeds_subdomain():
    url = "https://feeds.reuters.com/reuters/businessNews"
    assert extract_source_domain(url) == "reuters.com"

def test_extract_source_domain_empty():
    assert extract_source_domain("") == ""
    assert extract_source_domain(None) == ""

def test_domain_tier_scoring():
    config = DomainTiersConfig()
    assert config.get_tier_score("reuters.com") == 20
    assert config.get_tier_score("cnbc.com") == 15
    assert config.get_tier_score("nasdaq.com") == 10
    assert config.get_tier_score("unknown.com") == 5
```

#### Macro Buckets (`test_macro_buckets.py`)

```python
def test_macro_catalyst_fed():
    text = "Fed signals rate cut likely in Q2 as inflation cools"
    scores = score_all_buckets(text)
    assert scores["macro_catalyst"] >= 10

def test_geopolitics_tariff():
    text = "US announces new tariffs on China tech imports"
    scores = score_all_buckets(text)
    assert scores["geopolitics"] >= 8

def test_commodities_oil():
    text = "Oil prices surge on OPEC production cuts"
    scores = score_all_buckets(text)
    assert scores["commodities"] >= 6

def test_no_false_positives():
    text = "Apple announces new iPhone features"
    scores = score_all_buckets(text)
    assert all(s == 0 for s in scores.values())
```

#### Penalties (`test_penalties.py`)

```python
def test_penalty_stock_picks():
    text = "5 stocks to buy before the next bull market"
    penalty, patterns = calculate_penalty(text)
    assert penalty <= -10
    assert "stock_picks" in patterns

def test_penalty_price_target():
    text = "Analyst raises price target on NVDA to $500"
    penalty, patterns = calculate_penalty(text)
    assert penalty <= -8
    assert "price_targets" in patterns

def test_penalty_cramer():
    text = "Jim Cramer says this stock is a buy"
    penalty, patterns = calculate_penalty(text)
    assert penalty <= -10
    assert "pundit_content" in patterns

def test_penalty_cap_at_25():
    text = "Jim Cramer's top 5 stocks to buy - analyst upgrades"
    penalty, _ = calculate_penalty(text)
    assert penalty >= -25  # Capped

def test_no_penalty_clean_content():
    text = "S&P 500 closes higher on strong earnings"
    penalty, patterns = calculate_penalty(text)
    assert penalty == 0
    assert len(patterns) == 0
```

### Integration Tests

#### Score Distribution (`test_scoring_integration.py`)

```python
def test_score_distribution_spread():
    """Verify score distribution uses full range."""
    candidates = generate_test_candidates(100)  # Mix of content types
    results = score_candidates(candidates, config)
    
    scores = [r.impact_score for r in results]
    assert max(scores) >= 80, "Should have high scores for macro content"
    assert min(scores) <= 30, "Should have low scores for clickbait"
    assert statistics.stdev(scores) > 15, "Score spread should be wide"

def test_macro_ranks_above_clickbait():
    """Verify macro content consistently outranks clickbait."""
    macro_item = create_candidate(
        title="Fed announces rate cut, markets rally"
    )
    clickbait_item = create_candidate(
        title="5 best stocks to buy in 2026"
    )
    
    results = score_candidates([macro_item, clickbait_item], config)
    
    macro_score = next(r for r in results if "Fed" in r.title).impact_score
    click_score = next(r for r in results if "5 best" in r.title).impact_score
    
    assert macro_score > click_score + 20, "Macro should score 20+ pts higher"
```

### CLI Tests

```python
def test_evaluate_command_runs():
    """Verify evaluate command executes without error."""
    runner = CliRunner()
    result = runner.invoke(cli, ["score", "evaluate", "--top-k", "10"])
    assert result.exit_code == 0

def test_evaluate_verbose_output():
    """Verify verbose mode shows violations."""
    runner = CliRunner()
    result = runner.invoke(cli, ["score", "evaluate", "--verbose"])
    assert "Violations Detail" in result.output or "0" in result.output
```

---

## 9. Future Considerations

### Explicitly Deferred

1. **ML-based scoring (v3)**: Train classifier on human-curated top-K selections
2. **Publisher feed mapping**: Auto-discover domain from RSS content, not just URL
3. **Dynamic penalty weights**: A/B test penalty values based on CTR/engagement
4. **Cross-stream scoring**: Different weights for different market streams
5. **Real-time adjustment**: Boost breaking news based on velocity of similar items
6. **User feedback loop**: Allow operators to flag bad rankings for retraining

### Known Limitations

1. **Feed URL required**: Items without `feed_url` in metadata fall back to 5 pts
2. **Keyword brittleness**: Buckets require maintenance as terminology evolves
3. **Penalty false positives**: Legitimate "analyst downgrade" macro news may be penalized
4. **Single-stock earnings**: v2 may under-rank bellwether earnings (e.g., AAPL) that aren't "systemic"

### Potential Enhancements

1. **Entity recognition**: Use NER to identify companies, people, organizations
2. **Ticker mention scoring**: Boost multi-ticker mentions (sector-wide)
3. **Temporal patterns**: Boost items published near market open/close
4. **Source reputation scoring**: Track source accuracy over time

---

## Appendix A: Full Penalty Pattern Reference

| Pattern Name | Regex | Penalty | Examples |
|--------------|-------|---------|----------|
| stock_picks | `stocks?\s+to\s+buy\|top\s+\d+\s+stocks?...` | -15 | "5 stocks to buy", "top 10 stocks for 2026" |
| price_targets | `price\s+target\|analyst\s+(upgrades?\|downgrades?)...` | -10 | "analyst upgrades AAPL", "price target raised" |
| insider_activity | `insider\s+(sold\|bought)...` | -8 | "CEO sold 1M shares", "insider buying detected" |
| pundit_content | `jim\s+cramer\|motley\s+fool...` | -12 | "Jim Cramer says buy", "Motley Fool pick" |
| fomo_bait | `if\s+you('d\|.had)\s+invested\|millionaire-maker...` | -15 | "If you'd invested $1000", "millionaire-maker stock" |
| sensationalist | `why\s+\w+\s+crashed\|stock\s+soars...` | -8 | "Why Tesla crashed today", "Stock soars 50%" |
| earnings_noise | `beats?\s+estimates?\|misses?\s+estimates?...` | -5 | "beats estimates", "misses expectations" |
| listicle | `\d+\s+reasons?\s+why\|\d+\s+best...` | -10 | "7 reasons why", "10 best dividend stocks" |
| crypto_spam | `meme\s+coin\|to\s+the\s+moon...` | -8 | "Shiba to the moon", "next big crypto" |

---

## Appendix B: Macro Bucket Keywords

### MACRO_CATALYST (0-15 pts)
```
fed, federal reserve, fomc, powell,
cpi, pce, inflation, deflation,
gdp, nfp, nonfarm, payrolls, jobs report,
rate hike, rate cut, interest rate,
quantitative tightening, qt, quantitative easing, qe,
recession, soft landing, hard landing
```

### RATES_CREDIT (0-10 pts)
```
yield, yields, treasury, treasuries,
bond, bonds, credit spread, high yield,
default, sovereign, sovereign debt,
dollar, dxy, fx, forex, currency,
inverted yield curve, yield curve
```

### COMMODITIES (0-8 pts)
```
oil, crude, wti, brent,
gold, silver, copper, metals,
opec, opec+, lng, natural gas,
commodity, commodities
```

### GEOPOLITICS (0-10 pts)
```
tariff, tariffs, trade war,
sanctions, sanction, embargo,
war, conflict, military,
election, elections, vote,
china, russia, ukraine, taiwan, iran,
geopolitical, geopolitics
```

### SYSTEMIC_EARNINGS (0-8 pts)
```
profit warning, guidance cut, guidance lower,
major miss, significant miss, disappointing,
bellwether, sector-wide, industry-wide,
layoffs, mass layoffs, restructuring
```
