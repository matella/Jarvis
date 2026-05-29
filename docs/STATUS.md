# STATUS — read me first, update me last

> **Session protocol:** read this at the start of every session; update it at the end.
> It is the cheapest way to reload project state without re-reading the codebase.
> Keep it short. If a section grows past a few lines, the work belongs in a commit, not here.

## Current milestone
**M1 — Data model & contracts** · *DONE (acceptance passed against remote)*

## Done
- M0 (infra spine) DONE — see git history. Stack runs on remote `matella@192.168.129.85`
  via SSH docker context; healthcheck through the tunnel passes.
- M1 design recorded in `docs/superpowers/specs/2026-05-29-m1-data-model-design.md`
  (Alembic runner-only · TEXT+CHECK enums · prefixed ULID ids · raw psycopg3 · vector(768)).
- M1 built: Alembic migration `0001` (events/intents/executions/state/snapshots/memory,
  pgvector, CHECK constraints, HNSW cosine index); Pydantic `Event`/`Intent`/`Execution`/
  `MemoryRecord` + enums; `jarvis/ids.py`, `jarvis/db.py`; thin repositories; `MemoryStore`
  ABC + `PgVectorMemoryStore`.
- **M1 acceptance PASSED** on remote: migration applied (alembic_version=0001, all 6 tables,
  pgvector live); event→intent→execution share one `correlation_id` and round-trip;
  `MemoryStore` embedding round-trips + similarity search returns nearest. `pytest` 11/11,
  `ruff` clean.

## In progress
- *(nothing — ready to start M2)*

## Next step — do this first
Begin **M2 — event spine, zero AI**: Docker events ingester → Redis Stream → consumer group
→ `events` table → state **projector**; DLQ via consumer-group pending list → `jarvis:dlq`;
introspection CLI (`events tail`, `state show`, `inspect`, `trace`, `dlq`). The `state`/
`snapshots` Pydantic models land here with the projector (deferred from M1 by design).
See `docs/PLAN.md` for the M2 acceptance test.

## Open questions / blockers
- *(none)*

## Notes for next session
- Integration tests need the SSH tunnel up + `alembic upgrade head` already run.
- `state`/`snapshots` tables exist but have no Pydantic models yet — add them with the
  M2 projector (their only writer).

---
*How to update:* overwrite the four working sections (Current milestone / Done / In progress /
Next step). Move finished items out of "In progress" into a one-line "Done" entry. Don't let
"Done" accumulate detail — git history is the record; this file is the pointer.
