# Task 09: Implement generator LLM prompt + message renderer

## Status: COMPLETED

## Goal
Generate the final Telegram-ready message strictly from the facts bundle.

## Dependencies
- Depends on Task 08

## References
- `tasks/01_plan/spec.md` ((5) Output Format Contract: Telegram formatting + canonical section order)
- `tasks/01_plan/telegram_message.example.md`

## Scope
- Build prompts/templates for each mode:
  - `us_close` (daily)
  - `weekend_wrap`
  - `monday_preview` (conditional)
- Enforce the output contract from `tasks/01_plan/spec.md` (including `*Key Dates (UTC)*` and `*Sources*`).
- Ensure output is MarkdownV2-compatible (section markers, bullets, links/citations).
- Respect per-mode word/bullet limits from config.

## Acceptance criteria
- Given a fixture facts bundle, generation produces a correctly formatted message.
- The generator never introduces numbers/entities not present in the facts bundle.

---

## Implementation Summary

### Files Created

| File | Purpose |
|------|---------|
| `src/argus/generator/types.py` | Type definitions: `GenerationMode` enum, `GeneratorConfig`, `GeneratorResult`, `LLMGeneratedContent`, `NewsContext` dataclasses |
| `src/argus/generator/prompts.py` | System prompts for 3 modes, `build_news_contexts()`, `build_user_prompt()`, market/calendar formatting |
| `src/argus/generator/renderer.py` | MarkdownV2 escaping, section formatters (header, indices, takeaways, key dates, watch, spotlight, sources), `MessageRenderer` class |
| `src/argus/generator/generator.py` | `MessageGenerator` class with OpenRouter integration, retry logic, JSON parsing, error handling |
| `src/argus/generator/__init__.py` | Module exports for all public APIs |
| `tests/test_generator.py` | 50 comprehensive tests covering types, prompts, rendering, generation |

### Files Modified

| File | Changes |
|------|---------|
| `src/argus/config.py` | Added `GeneratorConfig` dataclass, wired into `StreamConfig`, YAML parsing in `ArgusConfig.load()` |
| `src/argus/cli.py` | Added `argus generate` command with `--bundle-file`, `--mode`, `--dry-run`, `--output` options |

### Architecture

```
FactsBundle → build_news_contexts() → NewsContext list with [1], [2] refs
    ↓
Build prompts (system + user) for mode
    ↓
Call OpenRouter API (GPT-4.1) with retry
    ↓
Parse JSON response → LLMGeneratedContent
    ↓
MessageRenderer assembles: header, indices, narrative, takeaways, dates, watch, spotlight, sources
    ↓
Apply MarkdownV2 escaping
    ↓
Return GeneratorResult
```

### Key Design Decisions

1. **Model**: OpenAI GPT-4.1 via OpenRouter (different from triage which uses Mistral)
2. **Two-stage rendering**: LLM generates narrative/takeaways/watch; Renderer assembles structured sections from bundle data
3. **Citation handling**: Pre-process news items to assign [n] numbers, LLM uses refs, renderer builds Sources section
4. **Index formatting**: Handled by renderer from bundle data (not LLM) - prevents hallucination
5. **Key Dates**: Populated from bundle's calendar_events; shows "No major events scheduled" if empty
6. **Error handling**: Retry once on LLM failure, parse markdown code blocks if present

### Configuration

```yaml
stream:
  generator:
    enabled: true
    model: "openai/gpt-4.1"
    temperature: 0.4
    max_retries: 1
    timeout_seconds: 60
```

### CLI Usage

```bash
# Dry-run (shows prompts without calling LLM)
argus generate --bundle-file bundle.json --dry-run

# Generate message
argus generate --bundle-file bundle.json --mode us_close

# Save output to file
argus generate --bundle-file bundle.json --output message.md
```

### Test Results
- 50 tests covering all modules
- All tests pass
- mypy: no issues
- ruff: no issues in generator module

## Completion Date
2026-01-07
