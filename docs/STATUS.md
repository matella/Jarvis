# STATUS — read me first, update me last

> **Session protocol:** read this at the start of every session; update it at the end.
> It is the cheapest way to reload project state without re-reading the codebase.
> Keep it short. If a section grows past a few lines, the work belongs in a commit, not here.

## Current milestone
**Phase 2 — Metrics ingest** · *DONE (acceptance passed live)* · (M0–M4 spine done before it)

## Done
- M0 (infra) + M1 (contracts) + M2 (event spine) + M3 (the model) DONE — see git history.
- M4 design in `docs/superpowers/specs/2026-05-29-m4-intent-loop-design.md`
  (dedicated contexts table · dry-run-under-observe gate · JSON-constrained agent).
- M4 built: migration `0002` (`contexts` provenance table); `core/context_store.py`;
  `tools/contract.py` + `tools/registry.py` (frozen tool contract + `docker.restart_container`
  capability-scoped executor); `agents/infrastructure.py` (one-shot `propose_intent` →
  IntentProposal JSON → validate vs capabilities → Intent adopting the trigger event's
  correlation_id; + `replay`); `intents/service.py` (approve/reject/execute; approval gate +
  mode gate: observe=dry-run/skipped, elevated=real executor, typed failure_class); router
  gains a `format` passthrough; CLI `intents propose/list/approve/reject/execute`,
  `inspect intent`, `explain`, `replay intent`.
- **M4 acceptance PASSED** live: agent proposed `docker.restart_container` (conf 0.95, risk
  medium, reversible) for a downed probe; gate blocked unapproved -> dry-run skipped under
  observe -> REAL restart under `JARVIS_MODE=assist` (exited->running); two executions share
  the trigger's correlation_id; `explain` surfaced the stored context (incl. a vector-relevance
  hit on the M3 summary memory); `replay` re-ran the model (same type, diff confidence/risk);
  `trace` showed the full event->intent->execution chain. `pytest` 49/49, `ruff` clean.

- P2 metrics ingest: `ingest/metrics.py` (docker stats + nvidia-smi poller),
  `ingest/metrics_store.py`, migration `0003` (`metrics` time-series table), config
  thresholds + `remote_ssh`; debounced threshold signal events (container.cpu_high/_normal,
  memory_*, gpu.*); CLI `metrics run` / `metrics show`. Raw samples → metrics table (NOT
  state/log, per Hard Rules); only signal events reach the spine.
- **P2 metrics acceptance PASSED** live: poller sampled 23 containers + GPU into `metrics`;
  `metrics show` displays usage; a CPU-burner crossed threshold → exactly one
  `container.cpu_high` (100.3%) + one `container.cpu_normal` on recovery (debounce works, no
  flooding). `pytest` 55/55, `ruff` clean.

## In progress
- *(nothing)*

## Next step — do this first
Pick the next Phase 2 piece (see `docs/PLAN.md` / `docs/ARCHITECTURE.md`): **alert correlation**
(now has metrics + lifecycle + signal events to correlate), reflect metrics signals into
`state.attrs` via the projector (clean follow-up), the **GPU scheduler** (telemetry exists),
operational journaling, or harden/observe. Pick a direction.

## Open questions / blockers
- *(none)*

## Notes for next session
- Integration tests need the SSH tunnel up (now incl. 11434) + `alembic upgrade head`.
- Live loop: `jarvis ingest` + `jarvis consume`; `jarvis summarize`; `jarvis intents propose <entity>`.
- Real execution requires `JARVIS_MODE` != observe (default observe = propose-only/dry-run).
- Reasoning defaults to `qwen3:8b`; set `MODEL_REASONING=llama3.2:latest` in `.env` for fast/cheap.
- `snapshots` table still has no model/writer (compaction comes later).

---
*How to update:* overwrite the four working sections (Current milestone / Done / In progress /
Next step). Move finished items out of "In progress" into a one-line "Done" entry. Don't let
"Done" accumulate detail — git history is the record; this file is the pointer.
