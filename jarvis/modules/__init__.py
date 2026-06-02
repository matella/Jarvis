"""Personal-OS module framework — shared backend helpers for user-document modules.

Every user-document module (tasks, notes, recipes, documents, local calendar) follows one shape
(see docs/specs/2026-06-02-shell-and-module-framework.md + docs/MODULE_TEMPLATE.md):

- a CRUD table it owns (the table is the source of truth, NOT the event log);
- graded tools (jarvis.tools.grading) — reversible/on-box/no-side-effects → auto-run;
- a light **awareness event** on significant change (a notice for the timeline + Jarvis context);
- a pgvector **search hook** (reuse the memory retrieval machinery — no new vector store);
- a read accessor the conversation agent's context assembly can call.

This package holds the cross-module pieces: `awareness.emit_awareness` and `search` (index/search/
purge over the shared `memory` table, `kind="module"`, `source` facet distinguishing modules).
"""
