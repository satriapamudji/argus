# Task 16: Reliable Citations + Filtered Sources

## Goal
Show only the sources that are actually cited in the generated message *and* ensure citations map to the correct underlying news items (even when the LLM mislabels numeric reference numbers).

## Problem Summary
### What we want
- If the message cites `[1]` and `[4]`, the `Sources` section should list only those two sources (renumbered sequentially if needed).

### What’s happening today
- Prompt provides numbered sources: `[1] Indian Shares`, `[2] Euro Zone Inflation`, `[3] Venezuela…`
- LLM talks about “Euro Zone Inflation” but sometimes cites it as `[1]` instead of `[2]`
- We extract `[\d+]` from the text and look it up → wrong source gets displayed
- To avoid mismatches, `format_sources()` currently lists **all** sources (ignoring the “only cited” requirement)

## Root Cause
Numeric reference numbers are brittle: the LLM sometimes “hallucinates” the index, so the number in the text cannot be trusted as a stable pointer back to the prompt’s numbered list.

## Proposed Approach (Deterministic)
Switch from **ordinal numeric pointers** to **stable per-source citation keys**, then post-process:

1. **Prompt:** Each news item includes a short, unique `CITE_KEY` (derived from URL hash or similar).
2. **LLM output:** LLM cites using `[{CITE_KEY}]` tokens (copy/paste), not `[n]`.
3. **Post-process:** We map keys → news items deterministically, then renumber keys to sequential numeric refs (`[1]..[k]`) for the final rendered message and `Sources` section.

This removes the “off-by-one ref number” failure mode entirely.

## Scope

### 1) Prompt changes (`src/argus/generator/prompts.py`, `src/argus/generator/types.py`)
- Add a per-item `CITE_KEY` to the formatted news context block (keep `[n]` for readability if desired, but instruct the model to cite only the key).
- Strengthen the system prompt with:
  - A hard rule: “Only cite using provided `CITE_KEY`s; never invent or renumber”
  - A concrete example showing correct usage

### 2) Parsing / extraction (`src/argus/generator/generator.py`, `src/argus/generator/renderer.py`)
- Replace/extend `extract_referenced_ids()` to:
  - Extract `CITE_KEY` tokens from `narrative + takeaways + watch_next`
  - Map `CITE_KEY` → `news_item_id`
  - Preserve first-seen order and dedupe (same behavior as today)
- Add compatibility behavior (decide one):
  - **Strict (preferred):** If no valid `CITE_KEY`s are found, treat as validation failure and retry generation with corrective prompt.
  - **Lenient:** Fall back to numeric `[\d+]` parsing (but then we cannot guarantee correct mapping).

### 3) Rendering / renumbering + sources filtering (`src/argus/generator/renderer.py`)
- Implement renumbering that replaces `[{CITE_KEY}]` with `[1]..[k]` consistently across:
  - `narrative`
  - `takeaways`
  - `watch_next`
- Update `format_sources()` to:
  - Include only referenced items
  - Use the same sequential numbering used in the renumbered text
- Remove the current “always show all sources” behavior in `format_sources()`.

### 4) Validation / retries (`src/argus/validator/validator.py` and/or generator retry loop)
- Add a generation-time check (pre-render) that:
  - Rejects unknown/hallucinated `CITE_KEY`s
  - Optionally requires at least 1–2 citations
- Ensure retry prompt explicitly mentions the exact citation format to fix.

### 5) Tests (`tests/test_generator.py`)
- Add unit tests for:
  - `CITE_KEY` extraction across all sections
  - Renumbering stability (same key → same number everywhere)
  - Sources filtering matches the renumbered references
- Add a regression test that simulates the original failure mode:
  - LLM “talks about source B” but uses an incorrect numeric `[n]`
  - With `CITE_KEY` citations, output remains correctly mapped and filtered

## Acceptance Criteria
- `Sources` lists **only** the sources cited in the final rendered message.
- Citation numbers in the message align with the `Sources` numbering.
- The system no longer depends on prompt-index `[n]` correctness for source mapping.
- Unknown/hallucinated citations cause retry or safe fallback (no mismatched sources displayed).
- All existing tests pass.

## Testing Commands
```bash
# Focused generator/renderer tests
pytest tests/test_generator.py -v

# Ensure validation still passes
pytest tests/test_validator.py -v
```

## Notes / Open Questions
- Decide whether fallback messages (no citations) should:
  - show all sources (useful), or
  - show none (strict “only cited”), or
  - cite all sources in the fallback narrative explicitly.
- Choose `CITE_KEY` format (short + unique + copyable):
  - e.g. 6–8 char base32/hex derived from `source_url` hash.

