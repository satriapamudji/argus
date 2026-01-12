# Task 27: Telegram Message Interactivity — Expandable Sections

## Overview

This task implemented expandable blockquotes for Telegram market update messages, allowing sections like Key Takeaways, Sources, and Key Dates to be collapsed by default and expanded on tap.

**Date Completed**: 2026-01-13
**Status**: ✅ COMPLETED (Phase 1 — Expandable Blockquotes)

## What Was Implemented

### Phase 1: Expandable Blockquotes (Completed)

Native Telegram expandable blockquote syntax was implemented for collapsible sections. This provides a clean UX without requiring callback infrastructure.

#### Key Changes

1. **Mode-Specific Message Formats** (`src/argus/generator/renderer.py`)
   - `_render_us_close()` — Original format (unchanged)
   - `_render_weekend_wrap()` — New format with collapsed sections
   - `_render_monday_preview()` — New format with collapsed sections
   - `format_header_windows()` — Mode-aware titles ("Weekly Wrap Up", "Monday Preview", "Market Update")
   - `format_weekly_stats_plain()` — Non-collapsed scorecard for weekend_wrap/monday_preview
   - `format_takeaways()` — Accepts custom header parameter

2. **Expandable Blockquote Syntax**
   ```markdown
   **>__Section Header__
   >• Bullet point 1
   >• Bullet point 2||
   ```
   - `**>` starts expandable blockquote (empty bold + blockquote marker)
   - Each line starts with `>`
   - `||` marks where content collapses (content after `||` is hidden until tapped)

3. **Mode-Specific Sections**

   | Section | us_close | weekend_wrap | monday_preview |
   |---------|----------|--------------|----------------|
   | Header | "Market Update" | "Weekly Wrap Up" | "Monday Preview" |
   | Index Snapshot | ✅ Plain | ❌ | ❌ |
   | Weekly Scorecard | Collapsed | **Plain** | **Plain** |
   | Cross-Asset Snapshot | ❌ | Collapsed | ❌ |
   | Narrative | ✅ | ✅ | ✅ |
   | Key Takeaways | "Investor Key Takeaways" (collapsed) | "Key Takeaways for the Week" (collapsed) | "Key Things to Look Out For" (collapsed) |
   | Key Dates | Collapsed | ❌ | Collapsed |
   | What to Watch | Collapsed | ❌ | ❌ |
   | Sources | Collapsed | Collapsed | ❌ |
   | Sign-off | ❌ | LLM-generated | ❌ |
   | Opening line | ❌ | ❌ | LLM-generated |

4. **LLM Content Extensions** (`src/argus/generator/types.py`)
   - Added `opening_line: Optional[str]` for monday_preview
   - Added `sign_off: Optional[str]` for weekend_wrap

5. **Updated Prompts** (`src/argus/generator/prompts.py`)
   - `SYSTEM_PROMPT_WEEKEND_WRAP` — Requests `sign_off` field, cross-asset analysis
   - `SYSTEM_PROMPT_MONDAY_PREVIEW` — Requests `opening_line` field
   - Added "NEVER round numbers" instruction to prevent LLM hallucinations

6. **Fallback Message Escaping Fix** (`src/argus/generator/generator.py`)
   - `_build_fallback_message()` now uses `escape_message_v2()` for proper MarkdownV2 escaping
   - Previously only escaped parentheses, causing HTTP 400 errors on publish

7. **Standalone Escaping Functions** (`src/argus/generator/renderer.py`)
   - `_escape_text_chars()` — Escape specific characters in text
   - `_escape_line_v2()` — Full line escaping with formatting preservation
   - `escape_message_v2()` — Complete message escaping (exported for use by generator)
   - `MessageRenderer._escape_message()` refactored to use standalone function

8. **Monday Preview News Window** (`src/argus/orchestrator/window.py`)
   - Changed `MONDAY_PREVIEW` window from 72h to 120h
   - Now captures full prior week's news content for context

9. **Validation Updates** (`src/argus/validator/validator.py`)
   - `_check_sections()` — Mode-aware required section validation
   - `_check_bullet_counts()` — Mode-specific takeaway header detection

### Files Modified

| File | Changes |
|------|---------|
| `src/argus/generator/renderer.py` | Added mode-specific renderers, expandable blockquote formatting, standalone escaping functions |
| `src/argus/generator/generator.py` | Mode-aware fallback messages, proper escaping, parse opening_line/sign_off |
| `src/argus/generator/prompts.py` | Mode-specific prompts with new output fields |
| `src/argus/generator/types.py` | Added opening_line, sign_off to LLMGeneratedContent |
| `src/argus/validator/validator.py` | Mode-aware section and bullet validation |
| `src/argus/orchestrator/window.py` | Changed monday_preview window to 120h |
| `tests/orchestrator/test_window.py` | Updated tests for 120h window |
| `tests/test_generator.py` | Added tests for mode-specific rendering |

### Test Results

- **574 unit tests pass**
- All existing tests continue to work
- New tests added for weekend_wrap and monday_preview format validation

## What Was NOT Implemented (Future Phase 2)

The original task spec included inline keyboard buttons for view switching. This was deferred:

- Inline keyboard buttons (`[📊 Full] [📰 Sources] [📅 Calendar]`)
- Message editing on button press
- Callback query handling
- View mode state management
- `editMessageText` and `answerCallbackQuery` bot API methods

These features would add complexity (callback infrastructure, state persistence) for marginal UX benefit. The expandable blockquotes provide 80% of the value with 20% of the complexity.

## Usage

Messages now render with native expandable sections:

```
*Weekly Wrap Up*
*13 Jan 2026*

__*Scorecard*__
Week: 6 Jan - 10 Jan
• S&P 500: +1.26%
• Dow Jones: +0.86%
• Nasdaq: +1.77%

**>__*Cross-Asset Snapshot*__
>• VIX: 14.2 (-5.3%)
>• 10Y UST: 4.76% (+8 bps)
>• DXY: 104.2 (+0.4%)||

[Narrative paragraphs...]

—————

**>__*Key Takeaways for the Week*__
>• First takeaway visible
>• Second takeaway hidden until tap||

**>__*Sources*__
>• [1] [Article Title](https://...)
>• [2] [Another Article](https://...)||

—————

Have a great weekend. See you Monday with the week ahead preview.
```

Users tap collapsed sections to expand them natively in Telegram.

## Dependencies

- Task 25 (Weekly Statistics) — Uses weekly stats for scorecard display
- Task 26 (CU Optimization) — Independent

## Notes

- Expandable blockquotes require Telegram client version 10.0+ (Dec 2023)
- Older clients show content as regular blockquotes (graceful degradation)
- The `||` collapse marker syntax is specific to Telegram's MarkdownV2
