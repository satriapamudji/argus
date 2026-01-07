# Task 00: Confirm decisions + close spec gaps

## Goal
Lock in the missing choices in `tasks/01_plan/spec.md` so implementation tasks are unblocked and the output contract is unambiguous.

## Questions to answer
- Tech stack: language/runtime (Python/Node/Go), framework (if any), packaging, and deploy target (Docker/VM/bare cron).
- Telegram formatting: parse mode (`Markdown` vs `MarkdownV2`) and escaping rules for the output contract.
- Output contract mismatch: should the final message include `*Key Dates*` and `*Sources*` sections like `tasks/01_plan/telegram_message.example.md`, or must it follow only the sections in `tasks/01_plan/spec.md`?
- Data providers + licensing:
  - Indices close + 1D deltas (S&P 500, Dow, Nasdaq)
  - Optional cross-asset (US10Y, DXY, WTI, gold/silver, VIX, sectors/breadth)
  - Calendar/catalysts source (macro/earnings/events) and timezone labels (SGT vs UTC)
- News ingestion: confirm the initial RSS feed allowlist content for `rss/us_close_basic.txt`.
- Full-text policy: confirm `allow_full_text_storage` and allowed snippet length for restricted sources.
- Monday preview gating: define how `risk_score` is computed and the default threshold/override behavior.
- Holiday/half-day logic: where holidays come from (calendar source) and desired default behaviors (skip vs publish closed note).

## Acceptance criteria
- Answers captured in an updated `tasks/01_plan/spec.md` and/or a concrete `config.yaml` draft.
- A final, explicit “Telegram message format contract” is agreed (sections + parse mode + escaping).

