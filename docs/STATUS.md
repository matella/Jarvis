# STATUS — read me first, update me last

> **Session protocol:** read this at the start of every session; update it at the end.
> It is the cheapest way to reload project state without re-reading the codebase.
> Keep it short. If a section grows past a few lines, the work belongs in a commit, not here.

## Current milestone
**Building the conversational-orchestrator program in order** (specs in `docs/superpowers/specs/`).
**8 Connectors + webhooks DONE** (live-verified). Next: 9 search + capture.
(6b UI follow-ups still pending: topology graph, metric charts, Cmd-K, Playwright.
 8 follow-ups: live CalDAV calendar connector; live IMAP/SMTP + HA against real instances.)

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
- **6a Conversational backend/gateway** (`gateway/` + `agents/conversation.py` + `conversation/`
  + migration 0011 `conversations`/`messages`): FastAPI `jarvis serve` with `/ws` (chat in →
  streamed `TurnResult` + presence transitions out), REST reads (events/state/incidents/intents/
  metrics), `/health` (from 5.5b), bearer-token auth → actor (open dev-mode when no token). The
  conversation agent is one-shot: NL + assembled context + memory window + capability summary →
  schema-constrained decision (route=answer|propose). confirm-to-act: a pending proposal + "yes"
  → approve+execute via the M4 gate, audited as `user:<actor>`. Presence states
  idle|listening|thinking|speaking|alert|frozen from spine state. Schema-constrained decoding
  (Ollama JSON-schema `format`) makes routing reliable on qwen3:8b.
- **6b React console + presence orb** (`web/` — Vite + React + TS + Tailwind, outside the python
  package): two surfaces over the 6a gateway — immersive **presence mode** (WebGL orb centerpiece)
  and **console/HUD** (live System/State/Incidents/Intent panels + compact orb). The **orb** is
  react-three-fiber with a custom simplex-noise/fresnel shader; color/turbulence/glow/sonar-rings
  are a pure `orbVisual(state)` map over presence (idle/listening/thinking/speaking/alert/frozen).
  WS client (auto-reconnect) + token auth; artifact renderers (markdown/table/status_grid/embed/
  image); confirm-to-act buttons send "yes"/"no" (UI never executes — the gateway gates). Cinematic
  command-deck aesthetic (Chakra Petch + IBM Plex Mono, teal/amber/steel). `npm run dev` (Vite
  proxies /api,/ws,/health → gateway). Vitest: 9 component tests (orb state machine + renderers).
- **7 Orchestration + action safety** (`orchestration/` + `core/planner.py` +
  `core/plan_executor.py` + `core/policies.py` + migration 0012 `plans`): the planner is one-shot
  (schema-constrained → a validated DAG of KNOWN capabilities; unknown → plan rejected; toposort
  rejects cycles). The executor is deterministic — walks steps in dep order, reads run queries,
  actions flow through the existing Intent→gate→executor (mode/approval/audit intact), all sharing
  the plan's correlation_id (one `trace`). Action safety: blast-radius (≤K entities) + rate-limit
  (≤N exec/window) pre-flight; **automatic rollback** of already-succeeded reversible steps on a
  later failure (tool contract gained `preview` for simulation + `revert`); reversible
  (rollback=automatic) actions are low-risk so semi_autonomous auto-runs them. CLI `jarvis plan
  make "<goal>" [--run|--simulate]`, `plan run/show`.
- **8 Connectors + webhooks** (`connectors/` + `gateway/webhooks.py`): read connectors emit
  sanitized events (`feeds` RSS/Atom → `feed.item`; `mail` IMAP → `mail.received`); act-Tools are
  gated like everything else (`mail.send` SMTP, `ha.set_state` HA REST with automatic rollback) —
  creds via SecretsProvider, outbound via egress allowlist. Inbound webhooks: gateway
  `/inbound/<source>` HMAC-verified → mapped events (github.push / grafana.alert / webhook.received).
  Connector ingest as opt-in daemon workers (`CONNECTORS_ENABLED`). CLI `jarvis connectors
  list/poll`. Injection content can shape a proposal, never act (verified).
- Latest: `pytest` 175/175, `ruff` clean (python); web `vitest` 9/9, `tsc`/`vite build` clean.
  Migrations at head = 0012 (8 needs none).

## In progress
- Conversational-orchestrator program, in order. **Next: 9** (search + capture), then 10
  (voice), scheduler (11), cross-cutting. Deferred: 6b UI slices (topology graph, charts, Cmd-K,
  Playwright); 8 live wiring (CalDAV calendar; real IMAP/SMTP/HA instances).

## Next step — do this first
Build **9** (search + capture) per its detailed spec in `docs/superpowers/specs/`. Self-hosted
SearXNG behind a SearchProvider interface; web fetch + capture as artifacts; egress-allowlisted.

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
