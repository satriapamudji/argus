# Task 23: Scoring v2 (Macro-First) Implementation

## Goal

Implement the Scoring v2 system as designed in `docs/design/scoring_v2_macro_first.md`. Replace `heuristic_v1` with `heuristic_v2` to fix source tier resolution, add macro-first category buckets, implement penalty system for clickbait, and provide CLI evaluation tooling.

## Background

Task 22 produced a comprehensive design document addressing three critical deficiencies in the current scoring system:

1. **Broken Source Tier Signal**: `source_name` contains RSS feed titles ("Markets") not publisher identity ("Reuters"), causing ~80% of items to fall to 5-point default
2. **No Penalty System**: Clickbait scores equivalently to macro news
3. **Score Compression**: Most items cluster in 40-55 range instead of using full 0-100 scale

Design document: `docs/design/scoring_v2_macro_first.md`

## Scope

### New Files to Create

| File | Purpose |
|------|---------|
| `src/argus/scoring/domain_tiers.py` | Domain extraction (`extract_source_domain()`) and tier resolution |
| `src/argus/scoring/macro_buckets.py` | Category bucket definitions (`MACRO_CATALYST`, `RATES_CREDIT`, `COMMODITIES`, `GEOPOLITICS`, `SYSTEMIC_EARNINGS`) and `score_all_buckets()` |
| `src/argus/scoring/penalties.py` | Penalty pattern definitions (`PENALTY_PATTERNS`) and `calculate_penalty()` |
| `src/argus/scoring/evaluate.py` | `run_evaluation()` logic for CLI command |
| `tests/test_domain_tiers.py` | Unit tests for domain extraction and tier scoring |
| `tests/test_macro_buckets.py` | Unit tests for category bucket scoring |
| `tests/test_penalties.py` | Unit tests for penalty pattern matching |
| `tests/test_scoring_evaluate.py` | Tests for evaluation command |

### Files to Modify

| File | Changes |
|------|---------|
| `src/argus/scoring/types.py` | Add `feed_url` to `ScoringCandidate`, add `source_domain` property; Update `ScoreBreakdown` to replace `keyword_relevance` with category buckets (`macro_catalyst`, `rates_credit`, `commodities`, `geopolitics`, `systemic_earnings`) and add `penalty` field |
| `src/argus/scoring/heuristics.py` | Replace v1 scorer with v2 logic: domain-based tier resolution, bucket scoring, penalty calculation |
| `src/argus/config.py` | Add `DomainTiersConfig` dataclass with tier lists and `get_tier_score()` method; Add to `ScoringConfig` |
| `src/argus/db/repository.py` | Update `get_candidates_for_scoring()` to include `raw_metadata->>'feed_url' AS feed_url` |
| `src/argus/cli.py` | Add `score` command group with `evaluate` subcommand |
| `config.yaml` | Add `domain_tiers` section under `scoring`, update `scorer_version` to `heuristic_v2` |

### Existing Tests to Update

Tests that verify `ScoreBreakdown` structure or `keyword_relevance` field will need updates:
- `tests/test_scoring_heuristics.py` — update expectations for new breakdown fields
- Any integration tests checking score breakdown structure

## Implementation Details

### 1. Data Model Changes

#### ScoringCandidate (types.py)
```python
@dataclass
class ScoringCandidate:
    # ... existing fields ...
    feed_url: Optional[str] = None  # NEW
    
    @property
    def source_domain(self) -> Optional[str]:
        """Extract normalized domain from feed_url for tier matching."""
        if not self.feed_url:
            return None
        return extract_source_domain(self.feed_url)
```

#### ScoreBreakdown (types.py)
```python
@dataclass
class ScoreBreakdown:
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
```

### 2. Domain-Based Source Tiers

#### DomainTiersConfig (config.py)
```python
@dataclass
class DomainTiersConfig:
    tier_1: list[str]  # 20 pts: reuters.com, bloomberg.com, wsj.com, ft.com
    tier_2: list[str]  # 15 pts: cnbc.com, marketwatch.com, barrons.com
    tier_3: list[str]  # 10 pts: yahoo.com, nasdaq.com, investing.com
    # Unlisted: 5 pts
    
    def get_tier_score(self, domain: str) -> int: ...
```

#### extract_source_domain() (domain_tiers.py)
- Parse URL, extract netloc
- Strip `www.` and `feeds.` prefixes
- Return lowercase domain

### 3. Macro-First Category Buckets

Five buckets with keyword lists and score caps:

| Bucket | Max Points | Points per Match |
|--------|------------|------------------|
| `macro_catalyst` | 15 | 5 |
| `rates_credit` | 10 | 3 |
| `commodities` | 8 | 3 |
| `geopolitics` | 10 | 4 |
| `systemic_earnings` | 8 | 4 |

See design doc Section 4.3 for full keyword lists.

### 4. Penalty System

Nine penalty patterns with regex matching:

| Pattern | Penalty |
|---------|---------|
| `stock_picks` | -15 |
| `price_targets` | -10 |
| `insider_activity` | -8 |
| `pundit_content` | -12 |
| `fomo_bait` | -15 |
| `sensationalist` | -8 |
| `earnings_noise` | -5 |
| `listicle` | -10 |
| `crypto_spam` | -8 |

Total penalty capped at -25.

See design doc Section 4.4 for full regex patterns.

### 5. Score Calculation Formula

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

impact_score = max(0, min(100, raw_score))
```

### 6. CLI Evaluation Command

```
argus score evaluate [OPTIONS]

Options:
  --stream TEXT           Stream name
  --window-hours INTEGER  Look back window [default: 24]
  --top-k INTEGER         Check top K items [default: 20]
  --verbose               Show individual violations
```

Exit codes:
- 0: Violation rate <= 10%
- 0 with warning: Violation rate 10-25%
- 1: Violation rate > 25%

### 7. Configuration Changes

```yaml
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

## Acceptance Criteria

### Functional

| ID | Criterion | Verification |
|----|-----------|--------------|
| AC-1 | Source tier correctly resolves for all configured feeds | Unit test: `cnbc.com` feed → 15 pts |
| AC-2 | Macro catalyst news scores 15+ points in category bucket | Unit test: "Fed cuts rates" → macro_catalyst >= 10 |
| AC-3 | Clickbait patterns receive negative penalty | Unit test: "5 stocks to buy" → penalty <= -10 |
| AC-4 | Score range spans 0-100 with meaningful distribution | Integration test: std dev > 15 across 100 items |
| AC-5 | CLI evaluate command runs without error | `argus score evaluate` exits 0 |
| AC-6 | Violation rate in top-20 < 25% | Evaluation on production data |

### Performance

| ID | Criterion | Verification |
|----|-----------|--------------|
| PC-1 | Scoring 100 items < 5 seconds | Benchmark test |
| PC-2 | No additional DB queries per item | Code review |
| PC-3 | Regex penalty matching < 1ms per item | Benchmark test |

### Quality Gates

- [ ] All existing scoring tests pass (with updated expectations)
- [ ] New unit tests for domain extraction, buckets, penalties
- [ ] Integration test showing score distribution improvement
- [ ] `argus score evaluate` shows < 25% violation rate
- [ ] Type checking passes
- [ ] Linting passes

## Out of Scope

- ML-based scoring (deferred to v3)
- Cross-stream scoring differences
- Historical re-scoring of existing items
- Source tier auto-discovery

## Risks / Notes

- Existing `keyword_relevance` field in `ScoreBreakdown` is being replaced — ensure all consumers are updated
- `feed_url` may be missing for older items ingested before `raw_metadata` included it — fallback to 5 pts
- Penalty patterns may have false positives on legitimate macro news (e.g., "analyst downgrade" of systemic importance) — monitor and tune

## Dependencies

- Task 22 (design document) — COMPLETED

## Estimated Effort

| Component | Estimate |
|-----------|----------|
| New modules (domain_tiers, macro_buckets, penalties, evaluate) | 2-3 hours |
| Update types.py, heuristics.py | 1-2 hours |
| Update config.py, repository.py | 1 hour |
| CLI command | 30 min |
| Unit tests | 2 hours |
| Integration tests | 1 hour |
| Config updates | 15 min |
| Verification & fixes | 1 hour |

**Total: ~8-10 hours**
