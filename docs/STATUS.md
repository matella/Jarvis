# STATUS — read me first, update me last

> **Session protocol:** read this at the start of every session; update it at the end.
> It is the cheapest way to reload project state without re-reading the codebase.
> Keep it short. If a section grows past a few lines, the work belongs in a commit, not here.

## Current milestone
**M2 — Event spine, zero AI** · *DONE (acceptance passed against remote)*

## Done
- M0 (infra spine) + M1 (data model & contracts) DONE — see git history.
- M2 design recorded in `docs/superpowers/specs/2026-05-29-m2-event-spine-design.md`
  (subprocess `docker events` · Typer+Rich CLI · focused container projector).
- M2 built: `ingest/docker_events.py` (allowlist mapping, drops `exec_*` noise);
  `events/stream.py` (Redis Streams helpers); `events/consumer.py` (consumer group,
  per-msg DB tx insert→project→ack, XCLAIM retry → `jarvis:dlq` after max_deliveries);
  `state/projector.py` + `state/models.py` (monotonic container projection via ULID
  last_event_id); `cli/main.py` Typer app (`jarvis` console script): ingest/consume/
  events tail/state show/inspect event/trace/dlq.
- **M2 acceptance PASSED** live on remote: created+restarted a throwaway `jarvis-m2-probe`;
  lifecycle events flowed Docker→Redis→consumer→`events`, `events tail` showed them, `state`
  projected to `running`, `trace`/`inspect`/`dlq` work. No model involved. `pytest` 21/21,
  `ruff` clean. (Probe + its events/state cleaned up afterward.)

## In progress
- *(nothing — ready to start M3)*

## Next step — do this first
Begin **M3 — add the model**: Ollama client + model-router policy behind a global inference
semaphore (concurrency=1); emit `model.loaded`/`inference.completed` timing events;
deterministic context assembly (recency + entity + vector relevance, ≤8K); one-shot
summarizer agent. **Acceptance:** `jarvis summarize --since 12h` grounded in real events,
with `inference.completed` timing events. See `docs/PLAN.md`.

## Open questions / blockers
- *(none)*

## Notes for next session
- Integration tests need the SSH tunnel up + `alembic upgrade head` already run.
- Run the spine live with: `jarvis ingest` (one shell) + `jarvis consume` (another).
- `snapshots` table still has no Pydantic model/writer (compaction comes later, not M3).

---
*How to update:* overwrite the four working sections (Current milestone / Done / In progress /
Next step). Move finished items out of "In progress" into a one-line "Done" entry. Don't let
"Done" accumulate detail — git history is the record; this file is the pointer.
