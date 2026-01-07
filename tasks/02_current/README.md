# Current Tasks (execution order)

Tasks 00-08 are completed and archived at `tasks/03_archive/`.

## Task list
- Task 09 (`tasks/02_current/09-task.md`): Generator LLM prompt + renderer (deps: 08)
- Task 10 (`tasks/02_current/10-task.md`): Validator + hallucination guard (deps: 08, 09)
- Task 11 (`tasks/02_current/11-task.md`): Telegram publisher + persistence (deps: 01, 02, 10)
- Task 12 (`tasks/02_current/12-task.md`): Run orchestrator + scheduling hooks (deps: 01, 02, 03, 05, 06, 07, 08, 09, 10, 11)
- Task 13 (`tasks/02_current/13-task.md`): Fixtures + docs/runbook (deps: 01, 08, 10, 11, 12)
