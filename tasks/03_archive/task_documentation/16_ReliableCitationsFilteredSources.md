# Task 16: Reliable Citations + Filtered Sources

## Summary
Made citations reliable by switching from brittle numeric references (`[1]`, `[2]`) to stable per-source cite keys (`[#A1B2C3D4]`) and post-processing them into consistent sequential numeric citations (`[1]..[k]`) in the final rendered message. The `Sources` section is now strictly filtered to include **only** sources actually cited in the message.

## What Was Before
- Prompt provided news items as an ordinal numbered list (`[1]`, `[2]`, `[3]`).
- LLM sometimes cited the wrong ordinal (off-by-one / mismatched), causing incorrect source attribution.
- To avoid mismatches, `Sources` was effectively forced to list **all** sources, violating the product requirement “show only cited sources.”

## What Changed

### 1. Stable cite keys added to news contexts (`src/argus/generator/types.py`, `src/argus/generator/prompts.py`)

- Added `cite_key` to `NewsContext`.
- Deterministic key generation:
  - `cite_key = sha256(source_url).hexdigest()[:8].upper()`
- Prompt formatting now includes the cite key token (e.g. `[#C9FB1023]`) alongside the human-readable ordinal index for readability.

### 2. Prompt rules updated to enforce cite-key citations (`src/argus/generator/prompts.py`)

- Updated the system prompt rules to require:
  - cite **only** using provided tokens in the exact format `[#A1B2C3D4]`
  - never invent or renumber citations
- Included explicit “correct vs incorrect” examples.

### 3. Strict citation extraction and validation (`src/argus/generator/renderer.py`, `src/argus/generator/generator.py`)

- `extract_referenced_ids()` now parses only cite-key tokens matching `\[#([0-9A-Fa-f]{8})\]`.
- Unknown/hallucinated keys raise an error (strict behavior).
- Generator enforces at least one citation in normal LLM output (no silent “uncited” content).

### 4. Renumbering and strict source filtering (`src/argus/generator/renderer.py`)

- Implemented renumbering:
  - Replace cite keys `[#........]` with sequential numeric refs `[1]..[k]`.
  - Applies consistently across:
    - `narrative`
    - `takeaways`
    - `watch_next`
- `format_sources()` now:
  - displays **only** referenced items
  - uses the same renumber mapping so the Sources numbering matches citations
  - if no citations, prints:
    - `__Sources__`
    - `• No cited sources.`

### 5. Updated offline smoke flow + fixtures (`src/argus/cli.py`, `tests/fixtures/generated_message_valid.md`)

- The offline smoke fixture was converted to cite-key format (LLM-style narrative containing `[#........]`).
- `argus smoke` now renders that fixture through the real renderer so the renumbering + filtered Sources behavior is exercised offline.

### 6. CLI helper to inspect DB message output (`src/argus/cli.py`)

Added a small helper to print the exact message content stored in the database:

```bash
# Show most recent message for a run
argus show --run-id 15

# Show a specific message by DB id
argus show --message-id 15

# Select raw/escaped/both
argus show --run-id 15 --format raw
```

This is useful to verify the final Telegram payload after an online run.

## Files Created/Modified

| File | Change |
|------|--------|
| `src/argus/generator/types.py` | **Modified** - added `cite_key` to `NewsContext`; prompt formatting includes `[#KEY]` |
| `src/argus/generator/prompts.py` | **Modified** - deterministic cite key generation + updated citation rules |
| `src/argus/generator/renderer.py` | **Modified** - strict cite-key parsing, renumbering, strict filtered sources |
| `src/argus/generator/generator.py` | **Modified** - require ≥1 cite key in LLM output; retry reminder; strict fallback Sources |
| `tests/test_generator.py` | **Modified** - updated unit tests for cite keys |
| `tests/fixtures/generated_message_valid.md` | **Modified** - now a cite-key narrative fixture (renderer produces final message) |
| `src/argus/cli.py` | **Modified** - smoke test now runs renderer for cite keys; added `argus show` command |
| `tasks/03_archive/16-task.md` | **Archived** - original task spec |

## Reasoning

Numeric ordinals are not stable identifiers for LLMs. Stable cite keys are deterministic, copyable pointers to sources that can be reliably mapped back to the bundle. Post-processing to numeric citations preserves the user-facing format while eliminating the “wrong index” failure mode.

## Acceptance Criteria Status

| Criterion | Status |
|-----------|--------|
| `Sources` lists only cited sources | Done |
| Citation numbers align with `Sources` numbering | Done |
| No dependency on ordinal `[n]` correctness for mapping | Done |
| Unknown citations cause retry/failure (no mismatched sources) | Done |
| All tests pass | Done |

## Test Results

- `pytest -q` → 487 passed, 5 skipped
- `python -m argus smoke` → PASSED
- Online end-to-end run (generate + publish) completed successfully (example: `argus run --stream us_close_basic --mode us_close`).
