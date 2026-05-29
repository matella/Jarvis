# STATUS — read me first, update me last

> **Session protocol:** read this at the start of every session; update it at the end.
> It is the cheapest way to reload project state without re-reading the codebase.
> Keep it short. If a section grows past a few lines, the work belongs in a commit, not here.

## Current milestone
**Phase 4 (started) — Contextual notifications** · *DONE (acceptance passed live)*.
Phase 3 trio also done (deploy awareness · `jarvis run` daemon · code-change proposals).

## Done (one line each — git history is the record)
- **M0–M4 spine**: infra (pgvector+redis on remote via SSH context) · contracts
  (events/intents/executions/state/snapshots/memory, Pydantic+migrations) · event spine
  (docker→Redis→consumer→events→projector, DLQ, CLI) · the model (Ollama router, semaphore=1,
  context assembly, summarizer) · intent loop (agent→validated Intent→approval+mode gate→
  capability executor; contexts table; explain/replay).
- **Phase 2**: metrics ingest (0003) · alert correlation → incidents (0004) · topology (0005,
  grounds correlation) · operational journaling (derived view). GPU scheduling deferred-by-design.
- **Phase 3**: code-intelligence MVP (0006 code_chunks; secret-safe SSH indexer; coder Q&A) ·
  deployment awareness (0007 container_images → `container.deployed`, in journal + correlator) ·
  **`jarvis run` daemon** (`core/supervisor.py` supervises all 5 collectors; metric signals
  reflected into `state.attrs`) · **code-change proposals** (`agents/code_editor.py` +
  `code.edit_file` tool → M4 gate; capability-scoped, YAML-validated, backup, observe=dry-run).
- **Phase 4**: contextual notifications (`notify/` — rules-based notifier consumer on the spine,
  webhook channel, deduped; notifies on incidents + critical events; 6th `jarvis run` worker;
  notifier group starts at `$` so it never replays history). Set `NOTIFY_WEBHOOK_URL` to enable.
- Latest: `pytest` 98/98, `ruff` clean. Migrations at head = 0007 (no schema change in P4).

## In progress
- *(nothing)*

## Next step — do this first
Open menu (per `docs/PLAN.md`): **Phase 5 — ambient** (proactive/auto agents — e.g. the daemon
auto-runs correlation on alert bursts, or the infra agent auto-proposes a gated restart intent
when a watched container dies). Or remaining Phase 4 multi-node bits (deferred — premature with
one box). Or harden/observe. The notifier + daemon make ambient triggering a natural next step.

## Open questions / blockers
- *(none)*

## Notes for next session
- Integration tests need the SSH tunnel up (incl. 11434) + `alembic upgrade head`.
- Live loop today (manual): `jarvis ingest` + `jarvis consume` in separate shells; then
  `summarize` / `intents propose` / `correlate` / `code ask` / `deploy detect`.
- Real execution needs `JARVIS_MODE` != observe (default observe = propose-only/dry-run).
- Reasoning=`qwen3:8b`; set `MODEL_REASONING=llama3.2:latest` in `.env` for fast/cheap.
- Tunnel drops periodically (added ServerAliveInterval); restart with `make tunnel`-equivalent.
- `snapshots` table still has no model/writer (compaction comes later).
