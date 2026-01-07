# Task 06: Implement scoring service (heuristics + optional LLM triage)

## Goal
Score and rank news items for each run window to select the best 2-6 items.

## Dependencies
- Depends on Task 02
- Depends on Task 03
- Depends on Task 05

## References
- `tasks/01_plan/spec.md` ((3) Key Design Principles: two-stage LLM use, (8) Architecture: Scoring Service)

## Scope
- Heuristic scoring (recency, source, uniqueness, market relevance).
- Optional lightweight LLM triage to add:
  - labels/topics
  - a short "why it matters"
  - confidence/flags (rumor, opinion, low quality)
- Persist output into `news_scores` with reasons.

## Acceptance criteria
- Given a fixture set of items, the scorer produces stable rankings with explanations.
- LLM triage can be turned on/off without changing the rest of the pipeline.
