# Task 29: LLM Prompt Engineering — Eliminate Obvious Conclusions

## Goal

Improve LLM prompts in `src/argus/generator/prompts.py` to eliminate generic/obvious statements and produce sharper, more insightful market narratives.

## Current Status (2026-01-14)

- **Planning phase** — Root cause analysis complete
- Current prompts produce content-free tautologies
- User has good examples to share for pattern extraction

## Background

### Problem Statement

The current LLM prompts in `prompts.py` produce outputs with "obvious" conclusions — generic statements that add no insight:

| Type of Problem | Example |
|-----------------|---------|
| **Generic sentiment** | "Stocks rose as investors grew optimistic about earnings" |
| **Content-free filler** | "The Fed statement was closely watched by market participants" |
| **Tautological explanations** | "Yields rose on inflation concerns" |

These are content-free tautologies, not actionable insights. Institutional readers expect precise analysis of mechanisms, positioning, and second-order effects.

### Root Causes Identified

1. **No explicit prohibition** on clichés — prompts don't ban filler phrases
2. **No examples of bad vs good output** — LLM has no model of what "obvious" looks like
3. **Missing "why it matters" instruction** — prompts focus on "what happened" not mechanisms
4. **No emphasis on second-order effects** or non-obvious connections
5. **Tone guidance is neutral but not sharp enough** — allows safe, bland prose
6. **No requirement for contrarian or nuanced perspective**

## Proposed Improvements

### 1. Add "Anti-Cliché" Section to SYSTEM_PROMPT_BASE

Add before OUTPUT FORMAT section:

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

### 2. Add "Insight Density" Requirement

```python
INSIGHT DENSITY:
Each paragraph must contain at least ONE non-obvious insight:
- A specific mechanism (e.g., "gamma hedging flows amplified the move")
- A cross-asset divergence (e.g., "credit spreads tightened despite equity weakness")
- A positioning implication (e.g., "CTA trend followers are now 80% long US equities, leaving room for a deleveraging event")
- A second-order effect (e.g., "higher Treasury term premium is compressing equity valuations via discount rates more than earnings expectations")
```

### 3. Sharpen Style Guidelines

Replace current STYLE_GUIDELINES with:

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

### 4. Add Few-Shot Examples to Each Mode

For SYSTEM_PROMPT_US_CLOSE, add after "MODE: Daily US Close Update":

```python
EXAMPLE OUTPUT (learn the style):
{
  "narrative": "Today's 1.2% S&P gain masks a significant rotation: cyclical value outperformed growth by 340bp, the widest spread since March. This wasn't broad optimism — defensive sectors (utilities +0.1%, staples -0.3%) barely participated. The divergence suggests a reflation trade driven by the 10Y yield's 7bp jump to 4.28%, not risk-on appetite. Notably, credit spreads tightened 8bp even as high-beta underperformed, indicating institutional positioning rather than retail FOMO. [#A1B2C3D4] The Fed governor's comments on 'higher for longer' were taken as data-dependent, not dovish — Fed funds futures actually shifted 4bp hawkish, pricing 22bps of cuts by December vs 26bps pre-speech. This repricing occurred despite the S&P rally, revealing a disconnect between equity positioning and rate expectations. [#D4E5F6A1]",
  "takeaways": [
    "Today's rotation favors value over growth — if 10Y breaks 4.35%, expect further cyclical outperformance",
    "Credit/equity divergence suggests institutional de-risking into strength — watch next week's CPI for confirmation",
    "Fed funds now price <25bps cuts by December vs 40bps a week ago — this hawkish repricing is occurring alongside equity rallies, an unstable combination"
  ],
  "watch_next": [
    "Thursday's CPI: core <0.3% MoM would reinforce the 'no landing' narrative, supporting rotation trades",
    "CTA equity models: 80% long, leaving room for deleveraging if SPX drops below 4,400"
  ]
}
```

Add similar few-shot examples to:
- `SYSTEM_PROMPT_WEEKEND_WRAP` — different style (weekly recap)
- `SYSTEM_PROMPT_MONDAY_PREVIEW` — different style (forward-looking)

### 5. Modify DATA SPECIFICITY Section

Add emphasis on interpretation:

```python
DATA INTERPRETATION:
- Don't just report numbers — explain what they SIGNAL about market structure
- "Yield +5bps" is data; "real rates +4bps, inflation breakevens unchanged" is interpretation
- When you cite a data point, always answer: "what does this tell us about positioning/flows/mechanics?"
```

## Implementation Details

### Files to Modify

| File | Changes |
|------|---------|
| `src/argus/generator/prompts.py` | Add anti-cliché rules, insight density, few-shot examples |
| `src/argus/generator/prompts.py` | Sharpen style guidelines across all modes |
| `src/argus/generator/prompts.py` | Add data interpretation guidance |

### Specific Changes by Section

1. **SYSTEM_PROMPT_BASE** (lines ~16-60):
   - Add ANTI-CLICHÉ RULES section after line 27
   - Add INSIGHT DENSITY section after ANTI-CLICHÉ
   - Replace STYLE GUIDELINES section (lines ~51-54)
   - Add DATA INTERPRETATION to DATA SPECIFICITY section (lines ~32-41)

2. **SYSTEM_PROMPT_US_CLOSE** (lines ~62-76):
   - Add few-shot example after line 73
   - Sharpen focus language

3. **SYSTEM_PROMPT_WEEKEND_WRAP** (lines ~78-105):
   - Add few-shot example specific to weekly recap style
   - Emphasize non-repetition of weekly stats

4. **SYSTEM_PROMPT_MONDAY_PREVIEW** (lines ~107-134):
   - Add few-shot example specific to preview style
   - Emphasize risk scenarios

## User Preferences Confirmed

- **Eliminate ALL generic content**: sentiment statements, filler phrases, tautologies
- **Tone**: "Sharper but grounded" — can state non-obvious conclusions firmly if data-supported
- **User will provide good examples later** for pattern extraction

## Acceptance Criteria

| ID | Criterion | Verification |
|----|-----------|--------------|
| AC-1 | Anti-cliché rules added to base prompt | Code review |
| AC-2 | Insight density requirement added | Code review |
| AC-3 | Few-shot examples added for all 3 modes | Code review |
| AC-4 | Style guidelines sharpened | Code review |
| AC-5 | Generate test output and verify reduced obviousness | Manual review |
| AC-6 | No regression in citation accuracy | Validation pass |

## Quality Gates

- [ ] All three modes have few-shot examples
- [ ] Anti-cliché examples cover all problem types identified
- [ ] Style guidelines emphasize mechanism over description
- [ ] Output generation still works (no JSON parse errors)
- [ ] Type checking passes

## Testing Strategy

1. **Generate sample outputs** using existing facts bundles
2. **Compare before/after** to verify reduction in obvious content
3. **Extract patterns** from user's good examples when provided
4. **Iterate** on prompts based on output quality

## Out of Scope

- Changing the LLM model provider
- Modifying facts bundle structure
- Changes to message rendering
- Altering JSON output schema (except for mode-specific fields)

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

**Total: ~10.5 hours**

## References

- Current prompts: `src/argus/generator/prompts.py`
- Related: Task 28 (Crypto prompts can inherit improvements)
