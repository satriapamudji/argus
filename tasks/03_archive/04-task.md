# Task 04: Implement near-duplicate dedupe + diversity helpers

## Goal
Prevent near-duplicates and support topic diversity in selection.

## Dependencies
- Depends on Task 02
- Depends on Task 03

## References
- `tasks/01_plan/spec.md` ((9) Database & Retention Strategy: Dedupe & "too similar" prevention)

## Scope
- Compute and store a similarity signature (SimHash preferred per spec) for each item.
- Implement near-duplicate detection within a configurable window (e.g., 14 days) and threshold (e.g., Hamming <= 4).
- Store long-lived fingerprints (`news_fingerprints`) so duplicates remain blocked even after TTL drops content.
- Add a basic `topic` label mechanism (heuristic rules and/or LLM triage output) to support diversity constraints downstream.

## Acceptance criteria
- Near-duplicate items are flagged/blocked consistently within the configured window.
- Facts bundle selection can enforce a "no 2 items from the same topic" rule (configurable) using stored topic labels.
