# Task 22: Scoring v2 (Macro-First) Design Document

## Summary

Created a comprehensive design document for the Scoring v2 system to address critical deficiencies in the current `heuristic_v1` scorer. This was a **design-only task** with no code changes.

## Problem Statement

Three critical issues with current scoring:

1. **Broken Source Tier Signal**: `source_name` contains RSS feed titles ("Markets") rather than publisher identity ("Reuters"), causing ~80% of items to fall to 5-point default tier
2. **No Penalty System**: Clickbait content scores equivalently to genuine macro news
3. **Score Compression**: Most items cluster in 40-55 range instead of using full 0-100 scale

## Design Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Source tier resolution | Domain-based via `feed_url` | `source_name` is unreliable; `feed_url` domain is always accurate |
| Data model change | Add `feed_url` field to `ScoringCandidate` | Separate field, not full `raw_metadata` access |
| Scorer versioning | Replace v1 in-place | No side-by-side operation; simpler migration |
| Backward compatibility | None for source tiers | Switch entirely to domain-based tiers |
| Config format | New `domain_tiers` section | Clean separation from deprecated `source_tiers` |
| Penalty system | 9 regex patterns, capped at -25 | Covers stock picks, pundits, FOMO bait, listicles, etc. |
| Category buckets | 5 macro-first buckets replacing flat keywords | Hierarchical importance with per-bucket caps |
| CLI evaluation | `argus score evaluate` command | Audit scoring quality against policy |

## Deliverables

### Design Document Created

**Location**: `docs/design/scoring_v2_macro_first.md` (1,359 lines)

**Contents**:
1. Executive Summary
2. Goals & Non-Goals
3. Background (current state analysis with code references)
4. Detailed Design
   - Data Model Changes (`ScoringCandidate`, `ScoreBreakdown`)
   - Domain-Based Source Tier Mapping
   - Macro-First Category Buckets (5 buckets)
   - Penalty System (9 patterns)
   - Score Calculation Formula
   - CLI Evaluation Command
5. Configuration Changes
6. Migration Plan
7. Acceptance Criteria (6 functional, 3 performance)
8. Test Plan
9. Future Considerations
10. Appendices (full patterns and keywords)

## Key Design Elements

### Category Buckets

| Bucket | Max Points | Keywords |
|--------|------------|----------|
| `macro_catalyst` | 15 | fed, fomc, cpi, pce, inflation, gdp, nfp, rate cut/hike |
| `rates_credit` | 10 | yield, treasury, bond, credit spread, dollar, dxy |
| `commodities` | 8 | oil, crude, gold, opec, natural gas |
| `geopolitics` | 10 | tariff, sanctions, war, election, china, russia |
| `systemic_earnings` | 8 | profit warning, guidance cut, bellwether, layoffs |

### Penalty Patterns

| Pattern | Penalty | Examples |
|---------|---------|----------|
| `stock_picks` | -15 | "5 stocks to buy", "top 10 stocks" |
| `price_targets` | -10 | "analyst upgrades", "price target raised" |
| `pundit_content` | -12 | "Jim Cramer says", "Motley Fool" |
| `fomo_bait` | -15 | "if you'd invested", "millionaire-maker" |
| `listicle` | -10 | "7 reasons why", "10 best" |

### Expected Score Distribution

| Content Type | Expected Range |
|--------------|---------------|
| Breaking macro (Fed) | 80-100 |
| Major geopolitical | 70-90 |
| Quality market news | 50-70 |
| Standard earnings | 40-60 |
| Penalized content | 10-35 |
| Pure clickbait | 0-20 |

## Implementation Task

Task 23 was created for the actual implementation:
- Task file: `tasks/02_current/23-task.md`
- Estimated effort: 8-10 hours
- Scope: 4 new modules, 6 files to modify

## Related Files

- Design document: `docs/design/scoring_v2_macro_first.md`
- Task file: `tasks/03_archive/22-task.md`
- Implementation task: `tasks/02_current/23-task.md`
