# Task 22: Scoring v2 (Macro-First) — Reduce Equity Clickbait, Improve Source Signal

## Goal
Improve `news_scores` ranking so that **market-moving macro / geopolitics / credit / commodities** items reliably float to the top for the daily update, while **low-value equity clickbait** ("stocks to buy", "price target", "insider sold", etc.) is strongly downweighted.

This task is **investigation + design + acceptance criteria only** (no code changes yet).

## Background (Current Behavior)
### Current scoring pipeline
- Scoring worker: `src/argus/scoring/worker.py`
  - Pulls unscored candidates in a lookback window
  - Scores via `HeuristicScorer` (heuristic_v1)
  - Optionally applies OpenRouter LLM triage (`src/argus/scoring/llm_triage.py`)
  - Inserts into `news_scores`

### Provider selection / versioning
- Pipeline providers registry: `src/argus/pipeline/registry.py`
  - `stream.providers.scoring` is currently limited to: `{ "heuristic_v1" }`
  - Provider: `src/argus/pipeline/providers/scoring_heuristic_v1.py` wraps `ScoringWorker`
- Separate field: `ScoringConfig.scorer_version` (default: `"heuristic_v1"`) is stored into `news_scores.scorer_version` by the worker.

### heuristic_v1 inputs and score components
Implementation: `src/argus/scoring/heuristics.py`
- Total impact score is additive of:
  - Recency: **0–25** (exp decay; half-life 6h)
  - Source tier: **0–20** (`SourceTiersConfig.get_tier_score(candidate.source_name)`)
  - Keyword relevance: **0–30** (high/medium keyword lists + topic diversity bonus)
  - Uniqueness: **0–15** (min SimHash distance vs recent items)
  - Breaking/urgency: **0–10** ("breaking", "just in", etc.)

### Major issue: source tier signal is currently wrong for our feeds
Ingestion derives `source_name` from:
- RSS feed title (primary), or
- feed domain (fallback)

Code: `src/argus/ingestion/rss_parser.py:extract_source_name()`

Because many feeds have titles like "Markets", "Commodities", etc, `source_name` often is **not** a publisher identity (Reuters/Bloomberg/etc). Therefore tier mapping in `SourceTiersConfig` (defaults: Reuters/Bloomberg/WSJ/CNBC/FT/Yahoo/MarketWatch) will frequently fall back to **5 points**, compressing scores and allowing clickbait to surface.

### Observed false positives in live DB (Jan 7–8 sample)
Query (top 30 by `impact_score`) shows several low-value items scoring high:
- "Jim Cramer says investors should avoid buying stocks near their highs..." (45)
- "Is Now the Time to Buy 3 of the S&P 500's Worst-Performing Stocks of 2025?" (45)
- "If You'd Invested $2,000 in Nvidia 5 Years Ago..." (42)
- "Could This Millionaire-Maker AI Stock Double Again..." (42)
- "Why Globalstar Stock Crashed Today" (42)

Pattern scan among **top 100** by impact_score:
- "stocks to buy" pattern hit: **4**
- "beats estimates" pattern hit: **2**

Pattern scan among **top 200** shows additional clickbait like:
- "3 Top Dividend Stocks to Buy in January" (appears multiple times)
- "This [Company] Insider Sold ..." (35)

(Exact query performed via local python+psycopg2 against the configured `DATABASE_URL`.)

## Scope (Investigation / Design Deliverables)
### 1) Define the scoring objective precisely
Target stream: `us_close` (macro-first recap). Scoring should prioritize:
- Macro catalysts: inflation (CPI/PCE), jobs (NFP/claims), PMI/ISM, GDP, Fed/central banks, rates/yields
- Geopolitics and policy: tariffs/sanctions/war/major elections with market impact
- Commodities shocks: oil/gas disruptions, OPEC decisions, major moves in gold/copper, etc.
- Credit stress and systemic finance: bank stress, HY spreads, default risk, sovereign risk
- Earnings only when **systemic / surprise / guidance** (profit warnings, major miss, sector bellwether, large cap shock)

Strongly deprioritize:
- Generic equity explainers: "why X stock rose/crashed", "stocks to buy", "top dividend stocks", "price target", "insider sold", listicles

### 2) Restore a reliable "source quality" signal
Proposed direction (design only): use **feed identity** rather than feed title.
Inputs available today:
- `raw_metadata.feed_url` is stored for each RSS entry (see `src/argus/ingestion/rss_parser.py:parse_feed()`)
- `source_url` is the entry link

Design choices to decide:
- Compute `source_key` from `raw_metadata.feed_url` domain (preferred) or `source_url` domain.
- Add config mapping for domains → tier score OR explicit allowlist of high-quality domains.
- Keep existing `SourceTiersConfig` semantics, but key it off `source_key` instead of `source_name`.

Acceptance criteria for source signal:
- A Reuters feed should consistently tier as Reuters even if the feed title is "Markets".

### 3) Replace simple keyword scoring with macro-first buckets + penalties
Design a heuristic_v2 / macro_plus set of rules that:
- Scores in **buckets** with caps, rather than only additive keyword counts.
- Adds **explicit penalty rules** for low-value patterns.

Candidate design (to refine):
- Macro catalyst bucket: +0..X
- Rates/FX/credit bucket: +0..X
- Commodities bucket: +0..X
- Geopolitics bucket: +0..X
- Systemic earnings surprise bucket: +0..X
- Penalty bucket (negative): -0..Y

Key: allow meaningful separation so genuine macro shocks can score ~80–95 while listicles fall below ~25.

### 4) Evaluate with a minimal offline harness
Even before a full labeling effort, define an evaluation loop:
- Pull top-K from the DB by score for a fixed time window
- Count policy violations (clickbait patterns in top-K)
- Spot-check that macro catalysts appear in top-K when present

## Out of Scope (for this task)
- Implementing the new scorer provider (`heuristic_v2`) or changing `stream.providers.scoring` supported keys
- Migrating DB schema for streams (handled by Task 21)
- Adding new external ML dependencies

## Risks / Notes
- Current scoring provider registry only supports `heuristic_v1` (see `src/argus/pipeline/registry.py`). To land v2, we’ll need to add a provider + config key, and decide how `ScoringConfig.scorer_version` relates to provider selection.
- Multi-stream work (Task 21) will require stream-aware scoring queries and per-stream evaluation.

## Next Task (Implementation Plan Preview)
When we decide to implement:
1) Add `heuristic_v2` scoring provider in `src/argus/pipeline/providers/`
2) Extend registry supported keys to include `heuristic_v2`
3) Update scorer to compute new source_key-based tiering
4) Add penalty patterns and macro buckets
5) Add tests + a small DB-backed evaluation script/command

## Acceptance Criteria (for the eventual implementation task)
- In a representative 24h sample, top 20 contains **0–1** clickbait/listicle items.
- Major macro releases (CPI/jobs/Fed) and market-moving geopolitics reliably appear in top 10 when present.
- Reuters/Bloomberg-tier feeds consistently receive higher quality scores than generic aggregators.
- Score distribution uses more of 0–100 range (no longer compressed below ~55 under normal conditions).
