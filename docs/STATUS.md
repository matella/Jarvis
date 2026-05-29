# STATUS — read me first, update me last

> **Session protocol:** read this at the start of every session; update it at the end.
> It is the cheapest way to reload project state without re-reading the codebase.
> Keep it short. If a section grows past a few lines, the work belongs in a commit, not here.

## Current milestone
**Phase 2 — Topology awareness** · *DONE (acceptance passed live)* · (M0–M4 + P2 metrics + correlation before it)

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
- P2 metrics ingest DONE (migration 0003, poller, signal events) — see git history.
- P2 alert correlation: migration `0004` (`incidents` table), `incidents/` module
  (models + repository), `agents/correlator.py` (deterministic temporal-burst clustering of
  warning+ alerts, dedup, one-shot LLM root-cause per cluster, excludes Jarvis's own meta
  events by source), CLI `correlate` / `incidents list` / `incidents show`.
- P2 alert correlation DONE — see git history.
- P2 topology awareness: migration `0005` (`topology` edges table), `ingest/topology.py`
  (deterministic builder from docker inspect: depends_on / network_mode / same_project;
  `build_topology`, `edges_for`, `all_edges`), wired into the correlator's prompt
  ("Known dependencies" section), CLI `topology build` / `show`.
- **P2 topology acceptance PASSED** live: `topology build` derived real edges
  (qbittorrent→gluetun depends_on + network_mode); a grounded-correlation demo (dep routes
  through base) produced an incident whose root-cause CITED the network_mode dependency.
  `pytest` 67/67, `ruff` clean.

## In progress
- *(nothing)*

## Next step — do this first
Plan items remaining (see `docs/PLAN.md`): **operational journaling** (curated timeline), then
later phases (dev intelligence, distributed execution, ambient). GPU scheduler still premature
per DECISIONS (one inference path). Consolidation still parked (off-plan): reflect metric
signals into `state.attrs` + a supervised `jarvis run` daemon so the spine runs continuously.

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
