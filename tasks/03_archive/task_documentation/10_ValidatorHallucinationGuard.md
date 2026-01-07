# Task 10: Validator + Hallucination Guard

## Summary
Implemented a comprehensive hallucination guard and validation system for LLM-generated messages, ensuring all content is grounded in the Facts Bundle (the sole source of truth).

## What Was Before
- Basic `MessageValidator` class existed with minimal checks:
  - Section presence validation (required headers)
  - Bullet count validation (3-5 takeaways, max 3 watch next)
  - Basic citation reference validation (checking `[n]` is within range)
- No hallucination detection for numbers, URLs, or other claims
- No fallback mechanism when LLM generation failed
- Generator raised exceptions on failure

## What Changed

### 1. Enhanced Hallucination Guard (`src/argus/validator/validator.py`)

Added comprehensive checks:

| Check Type | What It Validates |
|------------|-------------------|
| **Citation References** | `[n]` references are within 1-N range of news items |
| **URL Validation** | Any URLs in message exist in bundle's `source_url` set |
| **Percentage Validation** | `%` values exist in bundle market data or news text |
| **BPS Validation** | Basis point values exist in bundle |
| **Large Number Validation** | Market-level numbers (5000.00, 38,000) exist in bundle |

Key implementation details:
- `LARGE_NUMBER_WITH_DECIMAL_PATTERN` only matches numbers with decimals or comma separators, avoiding false positives on year numbers (e.g., "2026" in date headers)
- Numbers are normalized (commas removed, decimal places standardized) for comparison
- Allowed numbers are extracted from: market snapshot, cross-assets data, news item titles/snippets/content

### 2. Fallback Mechanism (`src/argus/generator/generator.py`)

- Added `_build_fallback_message()` method that generates a safe message from bundle data only (no LLM)
- Fallback is triggered:
  - After 2 consecutive validation failures
  - If LLM call fails completely (network error, missing API key, etc.)
- Fallback message includes:
  - Header with date
  - Market snapshot (all indices with levels and changes)
  - Key dates section (if calendar events exist)
  - Sources section (all news items, no narrative)
- Changed `generate()` return type from `GeneratorResult` to `tuple[GeneratorResult, ValidationResult]`

### 3. Updated Callers

- `src/argus/cli.py`: Updated to unpack tuple return from `generate()`
- `src/argus/generator/__init__.py`: Added `ValidationResult` export

### 4. Expanded Test Coverage (`tests/test_validator.py`)

New tests added:
- `test_validator_hallucinated_url` - Detects URLs not in bundle
- `test_validator_hallucinated_percentage` - Detects percentages not in bundle
- `test_validator_hallucinated_large_number` - Detects large numbers not in bundle
- `test_validator_valid_numbers_from_bundle` - Verifies bundle numbers pass
- `test_validator_unbalanced_bold_markers` - Detects formatting issues

## Reasoning

From `tasks/01_plan/spec.md`:
> "Facts Bundle is the sole source of truth for the LLM"

This design enforces that principle by:
1. **Pre-generation**: Facts Bundle constrains what the LLM can write about
2. **Post-generation**: Validator rejects any claims not grounded in bundle
3. **Graceful degradation**: Fallback ensures a message is always delivered, even if LLM fails

The hallucination guard focuses on high-confidence checks (numbers, URLs, citations) rather than entity extraction which would require NLP and have lower precision.

## Files Modified

| File | Change |
|------|--------|
| `src/argus/validator/validator.py` | Added hallucination checks for URLs, percentages, bps, large numbers |
| `src/argus/validator/types.py` | Already had `ValidationResult` dataclass |
| `src/argus/generator/generator.py` | Added fallback mechanism, changed return type to tuple |
| `src/argus/generator/__init__.py` | Added `ValidationResult` export |
| `src/argus/cli.py` | Updated to handle tuple return |
| `tests/test_validator.py` | Added 5 new hallucination guard tests |
| `tests/test_generator.py` | Updated tests for tuple return; changed API key test to expect fallback |

## Acceptance Criteria Status

| Criterion | Status |
|-----------|--------|
| Validator rejects known-bad fixtures (missing sections, extra numbers) | ✅ Tests pass |
| Retry/fallback behavior is deterministic and auditable in DB | ✅ ValidationResult returned for persistence |

## Test Results

All 392 tests pass (2 skipped are expected integration tests).
