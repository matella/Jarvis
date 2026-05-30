# STATUS — read me first, update me last

> **Session protocol:** read this at the start of every session; update it at the end.
> It is the cheapest way to reload project state without re-reading the codebase.
> Keep it short. If a section grows past a few lines, the work belongs in a commit, not here.

## Current milestone
**Building the conversational-orchestrator program in order** (specs in `docs/superpowers/specs/`).
**5.5c Security primitives DONE** (live-verified). Next: 6a conversational backend/gateway.

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
- **Phase 4**: contextual notifications (`notify/` consumer + webhook). **Phase 5**: ambient
  reactor (`core/reactor.py` — spine consumer auto-runs the infra agent on container-down events
  → GATED proposal, observe-only, loop-safe, per-entity cooldown, off-switch `reactor_enabled`;
  7th `jarvis run` worker).
- **P5 mode state machine**: `core/modes.py` — persisted (migration 0008 `system_state`),
  runtime-settable (`jarvis mode [set]`), 4 modes via one `decide(mode,intent)` policy governing
  the execution gate (`intents/service`) AND the reactor (suspended on maintenance; auto-runs
  auto-safe proposals under semi_autonomous).
- **P5 predictive observability**: `ingest/predict.py` — deterministic least-squares trend
  projection over `metrics` → `*_trending` events (cpu/mem/gpu mem) when a metric is forecast to
  cross its threshold within the horizon; debounced; 8th `jarvis run` worker; notifier pages on
  `*_trending`; appears in journal. CLI `jarvis predict`.
- **P5 operational playbooks**: `playbooks/` module + migration `0009` (pgvector); operator
  authors procedures (`jarvis playbook add/list`); the infra agent retrieves relevant playbooks
  by similarity and injects "Relevant playbooks" into its proposal context (stored in
  context_ref for explain). Activates the M1 memory pillar.
- **5.5a Durability** (`ops/backup.py` + `state/snapshotter.py`): scheduled `pg_dump` via the
  postgres container → off-box copy on the Mac + a remote copy, retention; **DR drill**
  (`backup verify` restores into a scratch DB + sanity-checks); state **snapshots** as
  fast-restore checkpoints + `rebuild` (replay after snapshot) — events never pruned. Two new
  daemon workers (snapshot, backup). CLI `backup run/verify`, `snapshot write/rebuild`.
- **5.5b Self-observability + audit** (`ops/health.py` + `audit/log.py` + migration 0010
  `audit_log`): `jarvis self` (worker liveness via Redis TTL heartbeats beaten centrally by the
  supervisor, DLQ depth, stream pending, inference latency, dependency reachability) + periodic
  `selfcheck` worker emitting `jarvis.health` on degrade/recover transitions; `audit_log` with
  actor attribution on intents approve/reject/execute, mode-set, and reactor auto-execute;
  `jarvis audit` timeline. Two new daemon workers wired (snapshot from 5.5a, selfcheck).
- **5.5c Security primitives** (`security/` — no migration, library + config): `sanitize()`
  (secrets + PII: emails/phones/tokens/keys) + `wrap_untrusted()` (data-not-instructions framing)
  in `security/sanitize.py`; `security/egress.py` default-deny allowlist (`allowed`/`check_url`/
  `guarded_request`, subdomain match, `EGRESS_ALLOWLIST` config); `security/secrets.py`
  (`SecretsProvider`/`EnvSecretsProvider`, repr hides values, never logged/prompted); kill switch
  `jarvis kill` → maintenance (audited; reactor/executor re-check `get_mode()` per cycle).
- Latest: `pytest` 139/139, `ruff` clean. Migrations at head = 0010.

## In progress
- Conversational-orchestrator program, in order. **Next: 6a** (conversational backend/gateway),
  then 6b, 7, 8, 9, 10, scheduler (11), cross-cutting.

## Next step — do this first
Build **6a** (conversational backend/gateway) per its detailed spec in `docs/superpowers/specs/`.

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
