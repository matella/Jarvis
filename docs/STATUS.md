# STATUS — read me first, update me last

> **Session protocol:** read this at the start of every session; update it at the end.
> It is the cheapest way to reload project state without re-reading the codebase.
> Keep it short. If a section grows past a few lines, the work belongs in a commit, not here.

## Current milestone
**EVERYTHING BUILT** 🎉 — numbered program (5.5a–11) + cross-cutting (A–D) + 6b UI polish +
the entire backlog (#1–#11). Nothing left to code; only deploy-time external-service wiring remains.
- Numbered: hardening (5.5a/b/c) → conversational backend + React orb console (6a/6b) →
  orchestration + action safety (7) → connectors + webhooks (8) → search + capture (9) → voice +
  audio-reactive orb (10) → GPU scheduler (11).
- Cross-cutting: A routines · B feedback + eval/replay · C observability ingest · D memory governance.
- Backlog: outcome verification · auto-postmortems · anomaly detection · confidence/abstention ·
  time-travel diffs · graceful degradation · KB ingest · cost-aware caching · governance polish ·
  plugin SDK · mobile PWA.

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
- **9 Search + capture** (`search/` + docker-compose `searxng`): `SearchProvider` interface with
  `SearxngProvider` (JSON API via egress guard; results sanitized + capped). Web RAG
  (`search/rag.py`): retrieve (deterministic) → frame as untrusted data → ONE-shot synthesis with
  `[n]` citations + `search.performed` event. Conversation agent gained a `search` route (current
  external info → cited answer + sources table artifact). `search/capture.py`: Playwright
  screenshot → `image` artifact, egress-allowlisted (lazy import). CLI `jarvis search/capture`.
- **10 Voice + orb audio-reactivity** (`voice/` + gateway audio path + `web/` audio): STT
  (`voice/stt.py`, Whisper.cpp wrapper) + TTS (`voice/tts.py`, Piper) + wake gate (`voice/wake.py`,
  pure state machine — no buffering before wake). Gateway `/ws` now accepts `{kind:"audio"}` → STT
  → the SAME `conversation.respond` path → TTS audio back; graceful degrade when binaries absent.
  Frontend: mic capture + TTS playback via Web Audio `AnalyserNode` → shared `audioLevel` → the
  **orb blooms with the actual voice** (mic while listening, TTS while speaking); mic button in the
  composer. Voice adds no reasoning — pure transport; actions still gated + audited.
- **11 GPU scheduler** (`models/scheduler.py`): a priority queue in front of the one resident
  model generalizes the bare `Semaphore(1)`. `Priority` interactive(chat/voice) > plan > background
  (reactor/summaries); `select()` is pure (priority then FIFO, but prefers the resident model when
  the `SwapLimiter` is at its per-minute cap so we don't thrash); `BudgetLedger` enforces per-key
  token caps (a runaway routine can't starve the GPU). `inference.scheduled` events carry wait-time
  + queue-depth. Wired: conversation + RAG → INTERACTIVE, planner → PLAN, infra agent → BACKGROUND.
- **Cross-cutting A. Scheduled routines** (`routines/` + migration 0013): cron-ish proactive
  briefings over existing capabilities (summary/briefing/search); pure `is_due` (daily-at /
  interval); daemon worker (`routines`, 12th supervisor worker) fires due routines, change-aware via
  last_run, suspended under maintenance → `routine.completed` event + notification. CLI `routine
  add/list/run`. Live: a briefing composed incidents + summarizer into a grounded digest.
- **Cross-cutting B. Feedback + eval/replay harness** (`feedback.py` + `eval/` + migration 0014):
  operator 👍/👎 on proposals/incidents → `feedback` rows + `feedback.recorded` events (gateway
  `POST /feedback`, CLI `jarvis feedback`, console buttons on jarvis turns); `score()` aggregation
  is the adaptive-attention seed. **Eval harness**: pure `compare()` (drift = type/target change,
  NOT confidence wobble) + `replay_intent` re-runs a stored `context_ref` through the current model
  + `run_suite`/`recent_proposer_intents`; CLI `jarvis eval` reports drift (regression gate on
  model/agent change). Live: a replayed proposal flipped restart→investigate → flagged DRIFT.
- **Cross-cutting C. Observability ingest** (`ingest/prometheus.py` + `ingest/loki.py`): Prometheus
  PromQL instant queries sampled into `metrics` (kind="prometheus", reusing `insert_samples`) so the
  existing trend/correlation machinery uses real exporter data; Loki LogQL count queries → a
  `log.spike` event (severity warning) the correlator can fold into incidents. Pure parsers, egress-
  guarded fetch, opt-in daemon workers (`OBSERVABILITY_ENABLED`), CLI `jarvis obs prometheus/loki`.
- **Cross-cutting D. Memory governance** (`memory/governance.py`): `list_memories` / `forget`
  (→ `memory.forgotten` event) / `consolidate` (compact older `kind` memories — all but the N
  newest — into ONE higher-level summary via one inference → `memory.consolidated`; same compaction
  idea as snapshots, applied to semantic memory). `playbooks.delete_playbook`. CLI `jarvis memory
  list/forget/consolidate` + `playbook forget`; gateway `GET /api/memory`.
- **6b UI polish slices** (`web/` Insight surface + Cmd-K + inspector): new **Insight** surface
  (3rd TopBar toggle) with tabs — **Topology** graph (hand-rolled SVG ring layout, typed edges,
  live state tint), **Metrics** charts (per-container CPU/MEM sparklines + threshold overlay),
  **Approvals** queue (proposed intents → approve→gated-execute / reject inline). **Decision
  inspector** modal (intent + causal trace + explain context). **Cmd-K** command palette (global).
  New gateway reads: `/api/topology`, `/api/intent/{id}` (detail+trace+context),
  `POST /api/intent/{id}/approve|reject` (gated + audited). Pure viz helpers unit-tested; Playwright
  E2E harness (`web/e2e/`, run after `npx playwright install chromium`).
- **Backlog #1 Outcome verification** (`verify/` + migration 0015): after an execution settles, a
  DETERMINISTIC check judges whether the effect held (container running + no fresh failure events
  since) → a `verifications` row + `verification.completed` event, linked by correlation_id.
  Periodic `verify` worker (13th) + CLI `jarvis verify [--show]`. The substrate for trustworthy
  autonomy — confidence, learning, postmortems all key off whether actions actually worked.
- **Backlog #2 Auto-postmortems** (`agents/postmortem.py`): one inference over a resolved incident →
  structured postmortem (what/root-cause/resolution) + a suggested reusable playbook; stored as a
  `postmortem` memory record + `postmortem.generated` event. `adopt_playbook` deterministically
  embeds + inserts the suggested playbook (operator-confirmed). CLI `jarvis postmortem <id> [--adopt]`.
- Latest: `pytest` 219/219, `ruff` clean (python); web `vitest` 15/15, `tsc`/`vite build` clean.
  Migrations at head = 0015 (#2 needs none).

- **Backlog #3 Statistical anomaly detection** (`ingest/anomaly.py`): robust z-score (median/MAD)
  of each container metric's latest sample vs its own rolling history → `metric.anomaly` event
  (warning, debounced per entity+metric) — catches what fixed thresholds (P2) + linear trends (P5)
  miss. Pure `zscore`/`is_anomaly`; always-on `anomaly` worker (14th); CLI `jarvis anomaly`.
  Live: flagged 5 real anomalies against the homelab's metric history.

- **Backlog #4 Confidence + abstention** (`agents/conversation.py`): pure `should_abstain(conf,
  floor)`; a propose decision below `abstain_confidence_floor` (0.45) returns route=`abstain` with
  NO intent created ("not confident enough (NN%) to act"). `TurnResult.confidence` surfaced; web
  shows a confidence chip + ABSTAINED badge. Live: a 20%-confidence propose abstained, no intent.
- **Backlog #5 Time-travel / temporal diffs** (`state/timetravel.py`): `state_at(ts)` replays
  container events up to a timestamp through the SAME projection logic (in-memory) to reconstruct
  point-in-time state; `diff(t1,t2)` → added/removed/status-changed. CLI `jarvis state-at <ago>` +
  `jarvis diff <since> [--until]`. Live: reconstructed state 1h ago + diff over 24h.
- **Backlog #6 Graceful degradation** (`core/degrade.py` + migration 0016 `deferrals`): when the
  LLM is unreachable, the deterministic spine keeps running and reasoning is *deferred* (queued) +
  `reasoning.deferred` event, not crashed. `reasoning_available()` gates; reactor defers its
  proposal when the model is down; a `degrade` worker (15th) drains deferrals once it's back;
  failed replays bump attempts + stay queued. CLI `jarvis deferred [--drain]`.
- Latest: `pytest` 232/232, `ruff` clean (python); web `vitest` 15/15, `tsc`/`vite build` clean.

- **Backlog #7 Knowledge-base ingest** (`ingest/kb.py`): indexes runbooks/notes/wiki (markdown/text
  over SSH, reusing the P3 code-indexer's read/chunk helpers) into `memory` as kind="kb" —
  sanitized + embedded, so the conversation agent's existing vector retrieval grounds answers in
  your docs (no new retrieval path). CLI `jarvis kb index/search`. (Live needs a docs dir with
  markdown; remote homelab path has none, so it no-ops cleanly.)
- **Backlog #8 Cost-aware caching** (`models/cache.py`): bounded LRU embedding cache (deterministic
  (model,text) → vector) wired into `router.embed` — a hit skips inference. Deliberately NOT caching
  chat (would replay stale non-deterministic decisions) and NOT model-tiering (a 2nd model = swaps
  costlier than they save on one 8 GB GPU; the scheduler's swap limiter is the lever). CLI `jarvis
  cache`. Live: same text embedded twice → 1 hit, inference skipped.
- **Backlog #9 Governance polish** (`core/governance.py`): **freeze windows** — autonomous actions
  (reactor auto-exec + plan executor) held during configured `FREEZE_WINDOWS` (pure `is_frozen_now`,
  wraps midnight); **universal preview** — `docker.restart_container` gained `preview`, `jarvis
  intents preview <id>` shows what any intent would change; **proactive nudges** — selfcheck emits
  `governance.nudge` when proposals pile past threshold. Live: previewed a real restart intent.
- **Backlog #10 Plugin SDK** (`plugins/loader.py`): a YAML manifest declares a capability (Intent
  type) backed by a templated, egress-allowlisted HTTP call — NOT shell. `render` substitutes
  `{arg}` only from a declared allowlist with scalar values; `build_tool` registers into the same
  registry/gate/audit as built-ins (+ preview). Loaded at gateway startup + `jarvis plugins`;
  `PLUGINS_DIR` empty = none. MCP would bridge onto this same path. Boundary unchanged.
- Latest: `pytest` 249/249, `ruff` clean (python); web `vitest` 15/15, `tsc`/`vite build` clean.

- **Backlog #11 Mobile PWA** (`web/public/` + index.html + main.tsx): installable web app manifest
  (standalone, theme color, SVG orb icon), an offline-shell service worker (network-first navigation
  → cached shell; never caches /api or /ws), SW registered in production only, and responsive tweaks
  (top bar wraps, presence chat padded + safe-area, empty-state fits a phone). Live-verified on a
  375px viewport: orb fills the screen, manifest/icon served, layout clean.
- Latest: `pytest` 249/249, `ruff` clean (python); web `vitest` 17/17, `tsc`/`vite build` clean.

## Everyday-AI roadmap (post-backlog) — in progress
Goal: turn Jarvis from "a console I open" into "an assistant that knows me and reaches me".
Order: **1) notifications keystone → 2) memory (session history + facts) → 3) mail/RSS connectors.**
- **[1a DONE] ntfy push channel.** `notify/channel.py` is now a multi-channel fan-out (ntfy +
  generic webhook; Web Push slots in next). Self-hosted `ntfy` compose service (app profile,
  published for NPM). Config `ntfy_url`/`ntfy_topic`; gateway+daemon wired. Verified live: Jarvis
  published to ntfy and read it back (prio/tags correct). **Operator setup to RECEIVE on devices:**
  NPM proxy host → set `NTFY_BASE_URL`, choose `NTFY_TOPIC`, install the ntfy app + subscribe
  (enable "instant delivery" for self-hosted). See `.env.example`.
- **[1b SKIPPED-by-design] PWA Web Push** — ntfy already delivers to phone/desktop/Wear OS locally;
  Web Push would relay via Google FCM (not local-first) for marginal gain. Revisit only if wanted.
- **[2 DONE] Memory.** (a) Session history survives refresh: client persists the conversation id
  (`?cid`), gateway `resume_or_start` (ownership-checked) + replays a `history` frame on reconnect;
  Cmd-K "New conversation" starts blank. (b) Durable operator facts (migration 0017 `user_facts`,
  `memory/facts.py`, upsert by key): captured deterministically (explicit "remember …" → focused
  extraction, NOT the weak router) + injected into context every turn; personal questions answered
  from facts via a focused grounded inference (small-model reliable) and NEVER web-searched (privacy
  guard). CLI `jarvis memory fact set/list/forget`. Live: capture → cross-session recall → search
  all verified. NOTE: recall fidelity rises with a bigger reasoning model (1.7b needs the focused path).
- **[3 DONE-mechanism] Mail/RSS → summarized push.** Multi-account mail (`MAIL_ACCOUNTS` JSON of
  per-account secret KEY names; legacy single-account still works) → `mail.received` per account.
  New triage worker (`notify/triage.py`, opt-in `TRIAGE_ENABLED`, own consumer group at `$`):
  consumes `mail.received`/`feed.item`, ONE inference → {importance, summary} (content wrapped as
  untrusted), pushes via the ntfy channel only when importance ≥ `TRIAGE_MIN_IMPORTANCE` (the noise
  gate); degrades cleanly when the LLM is down. Curated FEED_URLS + egress note in `.env.example`.
  Live-verified: triage_item classifies+summarizes on the box. Operator plugs in mail creds + feeds
  (+ allowlist feed hosts) to go fully live.
- **[4 DONE] Home Assistant + Calendar/Reminders.**
  - HA **read-ingest** added (control `ha.set_state` already existed): polls `HA_WATCH_ENTITIES` →
    `ha.state_changed` on real change (opt-in `homeassistant` connector; HA_TOKEN secret).
  - **Calendar** (`connectors/calendar.py`, opt-in): ICS fetch (egress-guarded) → pure VEVENT parser
    (RFC-5545 unfolding) → `calendar.event` upcoming-in-horizon, deduped by UID.
  - **Reminders** (migration 0018, `jarvis/reminders.py`, ALWAYS-ON worker): "remind me to … in 10m"
    → deterministic trigger + focused {text, due_at} extraction → stored; due-check worker fires via
    notifier (⏰), marks fired. CLI `jarvis remind add/list/fire`. Live-verified end-to-end.
- **[mobile] decision: NO native app** — ntfy is the local-first push answer (native would relay via
  FCM/APNs). Recommended next client work = a mobile-first **PWA pass** (+ Capacitor only if "one app"
  is later wanted). Not built yet — candidate for next session.
- Model: operator moving `MODEL_REASONING` → `qwen3:4b` (lifts recall/triage/extraction fidelity).

## Building the backlog — ALL DONE ✅
1. Outcome verification · 2. auto-postmortems · 3. anomaly detection · 4. confidence/abstention ·
5. time-travel diffs · 6. graceful degradation · 7. knowledge-base ingest · 8. cost-aware caching ·
9. governance polish · 10. plugin SDK/MCP · 11. mobile PWA — all built, tested, committed.
(Deferred-as-premature, NOT built by design: knowledge graph, multi-user, multi-node, OS sandboxing.)

## Next step — do this first
**Everything in the program + cross-cutting + backlog is built.** Only deploy-time wiring remains
(stand up SearXNG/Prometheus/Loki/whisper/Piper/mail/HA; `npx playwright install` for E2E). Or seed
a deferred-as-premature item once reality justifies it (a 2nd box → multi-node; etc.).

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
