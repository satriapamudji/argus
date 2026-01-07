# Current Tasks (execution order)

Task 00 is completed and archived at `tasks/03_archive/00-task.md`.

## Task list
- Task 01 (`tasks/02_current/01-task.md`): Scaffold Python project + configuration (deps: none)
- Task 02 (`tasks/02_current/02-task.md`): Postgres schema + migrations (deps: 01)
- Task 03 (`tasks/02_current/03-task.md`): RSS ingestion worker (deps: 01, 02)
- Task 04 (`tasks/02_current/04-task.md`): Near-duplicate dedupe + diversity helpers (deps: 02, 03)
- Task 05 (`tasks/02_current/05-task.md`): Enrichment service (deps: 02, 03, 04)
- Task 06 (`tasks/02_current/06-task.md`): Scoring service (deps: 02, 03, 05)
- Task 07 (`tasks/02_current/07-task.md`): Market snapshot + calendar adapters (deps: 01)
- Task 08 (`tasks/02_current/08-task.md`): Facts bundle schema + builder (deps: 02, 04, 06, 07)
- Task 09 (`tasks/02_current/09-task.md`): Generator LLM prompt + renderer (deps: 08)
- Task 10 (`tasks/02_current/10-task.md`): Validator + hallucination guard (deps: 08, 09)
- Task 11 (`tasks/02_current/11-task.md`): Telegram publisher + persistence (deps: 01, 02, 10)
- Task 12 (`tasks/02_current/12-task.md`): Run orchestrator + scheduling hooks (deps: 01, 02, 03, 05, 06, 07, 08, 09, 10, 11)
- Task 13 (`tasks/02_current/13-task.md`): Fixtures + docs/runbook (deps: 01, 08, 10, 11, 12)

