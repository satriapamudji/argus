# Task 29: Prompt Engineering — Eliminate Obvious Conclusions

## Goal

Improve LLM prompts in `src/argus/generator/prompts.py` to eliminate generic/obvious statements and produce sharper, more insightful market narratives.

## Status

**Completed** (2026-01-14)

## Problem Statement

The LLM prompts were producing outputs with "obvious" conclusions — generic statements that added no insight:

| Type of Problem | Example |
|-----------------|---------|
| **Generic sentiment** | "Stocks rose as investors grew optimistic about earnings" |
| **Content-free filler** | "The Fed statement was closely watched by market participants" |
| **Tautological explanations** | "Yields rose on inflation concerns" |

These are content-free tautologies, not actionable insights that institutional readers expect.

## Root Causes Identified

1. No explicit prohibition on clichés — prompts don't ban filler phrases
2. No examples of bad vs good output — LLM has no model of what "obvious" looks like
3. Missing "why it matters" instruction — prompts focus on "what happened" not mechanisms
4. No emphasis on second-order effects or non-obvious connections
5. Tone guidance allows safe, bland prose
6. No requirement for non-obvious insights

## Solution Implemented

### 1. Added `DATA INTERPRETATION` Section

```python
DATA INTERPRETATION:
- Don't just report numbers — explain what they SIGNAL about market structure
- "Yield +5bps" is data; "real rates +4bps, inflation breakevens unchanged" is interpretation
- When you cite a data point, always answer: "what does this tell us about positioning/flows/mechanics?"
```

### 2. Added `ANTI-CLICHÉ RULES` Section

```python
ANTI-CLICHÉ RULES:
- NEVER state the obvious: "stocks rose on optimism", "investors reacted to news"
- NEVER use content-free phrases: "closely watched", "in focus", "key drivers"
- NEVER explain prices with sentiment: "up on hopes", "down on fears"
- INSTEAD: Explain mechanisms, positioning, flows, unintended consequences
- INSTEAD: Connect dots others miss: cross-asset signals, divergences, anomalies

Examples of BAD vs GOOD:
❌ "Tech stocks rose as investors grew optimistic about earnings"
✅ "Tech outperformed despite mixed earnings, suggesting positioning squeeze more than fundamentals"

❌ "The Fed statement was closely watched by market participants"
✅ "The Fed's language shift on 'moderate' vs 'solid' growth suggests data-dependency deepening, increasing near-term volatility risk"

❌ "Yields rose on inflation concerns"
✅ "The 10Y yield's 8bp jump came with real rates +5bp — the inflation narrative masks a growth repricing"
```

### 3. Added `INSIGHT DENSITY` Requirement

```python
INSIGHT DENSITY:
Each paragraph must contain at least ONE non-obvious insight:
- A specific mechanism (e.g., "gamma hedging flows amplified the move")
- A cross-asset divergence (e.g., "credit spreads tightened despite equity weakness")
- A positioning implication (e.g., "CTA trend followers are now 80% long US equities, leaving room for a deleveraging event")
- A second-order effect (e.g., "higher Treasury term premium is compressing equity valuations via discount rates more than earnings expectations")
```

### 4. Replaced `STYLE GUIDELINES` Section

```python
STYLE GUIDELINES:
- Narrative: 2-6 paragraphs of MECHANISTIC, not descriptive, analysis
  * Describe HOW markets move, not THAT they moved
  * Include SPECIFIC DATA POINTS (exact values, not approximations)
  * Show causal chains: X data → Y positioning → Z price action
  * Highlight anomalies, divergences, and non-linear effects
- Takeaways: 3-5 bullets with actionable, non-generic insights
  * Each must have a specific level, threshold, or actionable angle
  * Avoid: "monitor", "watch", "keep an eye on"
  * Prefer: "if X breaks Y, expect Z"
- Watch Next: 2-3 bullets on specific catalysts with binary outcomes
```

### 5. Added Few-Shot Examples to Each Mode

Created style-matching few-shot examples for:
- `SYSTEM_PROMPT_US_CLOSE` — Daily rotation analysis
- `SYSTEM_PROMPT_WEEKEND_WRAP` — Weekly cross-asset fragmentation
- `SYSTEM_PROMPT_MONDAY_PREVIEW` — Forward-looking binary outcomes

Each example demonstrates:
- Mechanistic explanations ("capital is staying invested but becoming more selective")
- Comparative context ("fastest pace in two years", "first time since 2019")
- Positioning-based insights ("institutional bearishness on crude near a 5-year high")
- Second-order effects ("policy support can compress spreads and directly influence borrowing costs")

## Files Modified

| File | Changes |
|------|---------|
| `src/argus/generator/prompts.py` | Added DATA INTERPRETATION, ANTI-CLICHÉ RULES, INSIGHT DENSITY, replaced STYLE GUIDELINES, added few-shot examples to all 3 modes |

## Testing

### Test Results (2026-01-14)

**US_CLOSE (Run ID 48)** ✅
- Published to Telegram (Message ID 90)
- Quality: Good mechanistic analysis
  - "geopolitical risk premium reasserted itself in cross-asset pricing"
  - "diplomatic de-escalation is off the table... raising the probability of supply disruptions"
  - "positioning is now more sensitive to exogenous shocks than to incremental improvements"

**MONDAY_PREVIEW (Run ID 50)** ✅
- Published to Telegram (Message ID 91)
- Quality: Good with nuanced insights
  - "volatility is being repriced but not yet spilling over into broader risk-off flows"
  - "positive sector-specific news is being overshadowed by macro and geopolitical crosscurrents"
  - "Boeing outsold Airbus for the first time since 2018... underscoring a shift in competitive dynamics"

**WEEKEND_WRAP (Run ID 49)** ⚠️
- Minimal content due to insufficient news data in bundle
- Expected behavior when lacking source material

## User Preferences Confirmed

- Eliminate ALL generic content (sentiment statements, filler phrases, tautologies)
- Tone: "Sharper but grounded" — state non-obvious conclusions firmly if data-supported
- User provided good output example for pattern extraction

## Key Patterns Extracted from User's Good Example

1. **"capital is staying invested but becoming more selective"** — mechanistic explanation of rotation
2. **"fastest pace in two years" / "first time since 2019"** — comparative context
3. **"driven by falling imports rather than collapsing exports"** — causal specificity
4. **"positioning data shows institutional bearishness... a setup that could amplify"** — contrarian insights
5. **"Davos window on 19-23 January" / "within one to two months"** — specific timelines
6. **"policy support can compress spreads and directly influence borrowing costs"** — second-order effects

## Dependencies

- None — standalone prompt improvement task

## Estimated Effort

| Component | Estimate |
|-----------|----------|
| Draft anti-cliché rules with examples | 1 hour |
| Draft insight density section | 0.5 hours |
| Create few-shot example for US_CLOSE | 1.5 hours |
| Create few-shot example for WEEKEND_WRAP | 1.5 hours |
| Create few-shot example for MONDAY_PREVIEW | 1 hour |
| Implement all changes in prompts.py | 1 hour |
| Test generation and review outputs | 2 hours |
| Iterate based on user examples | 2 hours |

**Total: ~10.5 hours** (actual may vary)

## References

- Current prompts: `src/argus/generator/prompts.py`
- User's good output example (shared 2026-01-14)
- Task file: `tasks/03_archive/29-task.md`
