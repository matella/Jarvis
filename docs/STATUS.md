# STATUS — read me first, update me last

> **Session protocol:** read this at the start of every session; update it at the end.
> It is the cheapest way to reload project state without re-reading the codebase.
> Keep it short. If a section grows past a few lines, the work belongs in a commit, not here.

## Current milestone — "Make Jarvis smarter" program (live on the box)
- **Wave 0 (done):** behavioral eval — `jarvis/eval/{behavior,cases}.py`, 108 example use-cases,
  `make eval` (GPU-free routing regression). `fastpath_route()`/`_present_target()` now the single
  routing source of truth shared by `respond()` + the eval. Caught/fixed 2 false-positives.
- **Wave 1.0 (done):** coding-aware answering — `_Decision.domain`, `jarvis/agents/environment.py`
  (env block #6), `conversation._code_answer()` (coder model / Claude under a coding-expert template,
  #1/#3/#17). Spec: `docs/superpowers/specs/2026-06-05-coding-aware-answering-design.md`.
- **Wave 2 (done):** correctness discipline — `jarvis/agents/code_validation.py` (ast.parse/json
  syntax-check of generated code) + self-correct re-ask (#24), "say when unsure" clause (#20).
- **Wave 1.2 (done, ENABLED on box):** execute-to-verify — `jarvis/agents/code_sandbox.py` runs
  generated Python in an ephemeral `docker run --network none --read-only --cap-drop ALL` container,
  re-asks once on a real traceback (#11/12/13). Gateway now mounts `/var/run/docker.sock` (same as
  the daemon) + `CODE_EXEC_ENABLED=true` in box .env. Verified live: clean run, traceback capture,
  and network isolation (`Network is unreachable`).
- **Wave 5 (done):** exact-compute — `jarvis/agents/calc.py`, AST-whitelist evaluator + strict
  detection, `fastpath_route → "math" → _compute_answer` (#21, zero inference).
- **Wave 4 (done):** escalation ladder — `_should_escalate`/`_plain_answer(backend=)`: empty LOCAL
  answer retries once on Claude so Jarvis never goes silent (#2).
- **Wave 5b (done):** conservative coding-answer cache — `jarvis/agents/answer_cache.py`, checked at
  the top of `_reason` so a repeated self-contained coding question short-circuits the whole pipeline
  (#22). Verified live: 68s → 0.002s on repeat. Back-references/short fragments never cached; 6h TTL.
- **Wave 3 (done):** recency-search prompt nudge (#7). Grounding over the operator's own data
  (#5/#8/#16) already runs via `assemble_context` (pgvector RAG) — no new ingestion needed.
- **Deliberately deferred (rationale):** #4 self-consistency (N× inference cost) · #9 few-shot store
  (infra; partly covered by RAG) · #15 scratchpad (low value with thinking models) · #18
  critic-as-extra-pass (cost; syntax+exec verify already cover coding). #23 feedback capture already
  exists (cross-cutting B). [#22 answer cache: now BUILT — see Wave 5b.]
- **Note:** first-time coding answers are ~slow (~60-70s: routing + specialist `claude -p` call +
  sandbox run); the cache makes exact repeats instant (0.002s). Latency is dominated by `claude -p`.
- **Wave 6 (done):** answer-QUALITY eval — `jarvis/eval/quality.py` + `quality_cases.py`, LLM-as-
  judge over the full pipeline; `make eval-quality` (run on box). Live result: **14/15, mean 0.94**
  (coding/knowledge/math all 1.00). It surfaced + we fixed a real misroute (self-capability
  questions like "can you restart a container?" were classified domain=coding → lost the persona;
  domain rule now reserves coding for programming help). One strict-judge near-miss left
  (architectural self-description) — accepted, not overfit.

## Homelab apps deployed + plugged into Jarvis (2026-06)
- **HotS Patch Notes** (`~/apps/hots` on box): api :5001 + web :5100, SQLite, sync working (pulls
  current patches). `jarvis/connectors/hots.py` → "latest hots patch" / "hots heroes" present cards.
- **Orpheus** (`~/apps/orpheus`): server :3010 + client :8085, AI off (no GPU contention), Spotify
  dormant (placeholder creds — add real `SPOTIFY_CLIENT_ID/SECRET` in `~/apps/orpheus/server/.env`).
  `jarvis/connectors/orpheus.py` → "what's orpheus playing" (says "running, Spotify not connected"
  until creds added). Spec: `docs/superpowers/specs/2026-06-05-external-apps-deploy-integrate-design.md`.
- **HotS Overlay** (`~/apps/hots-overlay`): Node + MongoDB, overlay :8086, mongo-express :8087.
  `jarvis/connectors/hots_overlay.py` → "show my recent hots matches" (empty until the gaming-PC
  replay uploader runs + `TOON_HANDLE` set in `~/apps/hots-overlay/.env`). Healthcheck overridden to
  :8086 (compose override). `_present_hots` disambiguates: matches/overlay → overlay, patch/hero → notes.
- **world-news-full** (`~/apps/world-news`, compose under `docker/`): Rust GraphQL gateway :8000 +
  scraper + ai :9002 + Next.js :3012, postgres :5433. It's a SKELETON (GraphQL exposes only
  `hello`, no articles). `jarvis/connectors/world_news.py` reports status (placeholder for real
  resolvers later). Fixed a real bug: api-gateway bound `127.0.0.1` inside the container → patched to
  `0.0.0.0` (applied to local repo + box). "world news status" → reachable + the stub greeting.
- Both auto-observed by the Jarvis daemon (Docker socket). Read-only present/query only (no control).
  Box egress allowlist gained `host.docker.internal`. Redeploy an app: edit `~/apps/<x>`,
  `docker compose up -d --build`.

## World News — COMPLETE & LIVE (engine + independent newspaper site)
- **Full system live on box.** Engine (`jarvis/news/`): scrape (stdlib RSS, guarded) → ingest
  (idempotent + `news.article_scraped`) → embed (**snowflake-arctic-embed2** 1024d CPU; bge-m3 was
  dropped — emitted NaN) → pool/cluster (sim **0.70**, origin-collapse, per-article commit) →
  tier-A summary+tags (**pinned local** qwen3:1.7b — was wrongly hitting Claude → 10× slowdown) →
  tier-B synthesis (grounded/cited/disagreement-aware). Daemon workers: news_scrape (hourly),
  news_process (60s), news_publish (5min). Daily `news_brief` routine seeded (07:30).
- **Clustering works:** cross-outlet same-event stories merge (multi-source up to 3 articles).
  Orphan-prune + reconciling publish keep both stores clean.
- **Independent site** (`world-news-full`, Next.js :3012): reads its OWN Postgres (`published_stories`,
  written by Jarvis's publisher), so it serves even if Jarvis is down. **Themeable newspaper** front
  page: `?paper=cream|crisp|sepia|ink & ?density=airy|normal|dense & ?font=serif|blackletter|slab &
  ?masthead=…` (or NEWS_* env defaults). Retired the Rust api-gateway/ai-service (no Rust).
- **Config on box:** NEWS_ENABLED=true, WORLD_NEWS_DB_URL set, source domains in EGRESS_ALLOWLIST,
  snowflake-arctic-embed2 pulled. Frontend reads `/graphql` no longer — it queries Postgres directly
  (so NPM just needs the home-page proxy).
- **Newspaper site polished:** themeable (paper/density/masthead/font via ?params or NEWS_* env),
  **topic sections** (World/Belgique/Tech&Business/Sport from story.topic), **story snippets** +
  clickable **/story/[id] deep pages** (synthesis + "where sources disagree"), **Ask-Jarvis** links
  (open the console via `?ask=` deep-link, which auto-sends). **/admin dashboard**: pipeline stats
  (articles/pending/stories/multi-source/published, by-lang, last-ingest) + a DB-down banner.
- **Synthesis made continuous + visible:** a `news_synthesize` worker writes the full tier-B
  synthesis for multi-source stories as they form (bounded 3/cycle, self-limiting; single-source
  stay on their tier-A summary) — no longer only at the 07:30 edition. Published `body` falls back
  to the tier-A summary so every story has content (no empty "still developing"). Admin shows
  synthesis done/awaiting + process & synthesis ETAs + a per-story status chip (Full / Synthesising
  / Summary). Belga dropped — no public RSS (its dispatches arrive via RTBF/Le Soir/La Libre).
- **Box ops (this session):** disk hit 100% (Postgres → recovery → empty edition). Root cause: the
  Ubuntu LVM default left ~130GB unallocated — operator ran `lvextend -l +100%FREE` + `resize2fs`
  → **disk now 226G, ~143G free**. Also retired the unused world-news Rust services (api-gateway/
  ai-service/scraper) — world-news = postgres + frontend only, both `restart: unless-stopped`.
  Periodic `docker builder prune` advised if rebuild cache grows. publish() guards empty-wipe +
  reconciles the read-model. 472 unit tests + 123 eval cases green.
- **Remaining (optional):** cross-language event grouping (v2) · clustering threshold fine-tune.

## (superseded) World News build — BACKEND LIVE (M1–M3 done; plan: docs/superpowers/plans/2026-06-07-world-news-jarvis.md)
- **M1–M3 DONE, deployed, verified with REAL news on box.** `jarvis/news/`: models (canonical_hash
  dedup) · embedding (bge-m3 1024d CPU + cosine) · pooling (cluster + origin-collapse) · repository
  (idempotent upsert, nearest_story SQL, vector search, top-by-coverage) · reactor (embed→pool→
  tier-A, representative-only) · ingest (idempotent + `news.article_scraped` event) · worker
  (`scrape_once` + `process_pending` backlog drainer) · fetch (stdlib RSS via guarded_request,
  reuses parse_feed) · sources (10 feeds, broad mix) · synthesis (tier-B grounded/cited/
  disagreement-aware). Migration `0029_news`. Present route `news` + semantic search + capability.
  Daily `news_brief` routine action. Supervisor runs `news_scrape` (hourly) + `news_process` (60s).
- **Live verified:** real BBC/world headlines pooled into stories; "what's the world news?" → cards;
  tier-B synthesis grounded + cited. ~10 news test files, suite green (470).
- **Enabled on box:** `NEWS_ENABLED=true`, `bge-m3` pulled, source domains added to EGRESS_ALLOWLIST.
- **Remaining:** create a daily `news_brief` routine instance (one API/UI step) to push the briefing.
  **M4:** Next.js standalone UI (separate plan; mockups in `world-news-full/.superpowers/brainstorm/`).
- **Tuning notes:** clustering threshold 0.82 may merge/split — watch (1-src) stories as volume grows.

## Prior milestone
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

## Personal-OS arc (post-everyday-AI) — in progress
Foundation locked in `docs/specs/2026-06-02-personal-os-foundation.md` (two data classes:
operational state vs user-owned CRUD docs; graduated gate; deterministic harnesses; module
framework). Sub-projects each get spec → plan → build.
- **[#1 Multi-backend router DONE]** local (Ollama) + claude (`claude -p`, subscription) behind
  `scheduler.chat`, **default local** (zero behavior change until `jarvis model claude`). `backends/`
  (resolve, breaker+budget, caged claude, persisted `system_state.llm_backend`) + dispatch fork
  (schema-validate-then-fallback, breaker on rate-limit, `inference.completed` gains `backend`) +
  conversation local-routes/Claude-composes + postmortem pilot + `jarvis model` CLI + Node/claude CLI
  in the image + `make claude-token`. Spec+plan: `docs/specs/2026-06-02-multi-backend-router*.md`.
  Spike-verified auth = `CLAUDE_CODE_OAUTH_TOKEN` env. Merged to main; 261 tests green. **To go live:**
  `make claude-token` → token in box `.env` → `git pull && make deploy` on the box → `jarvis model claude`.
- **[ENTIRE ARC SPECCED 2026-06-02]** Every module now has a spec+plan file under `docs/specs/`
  (one self-contained file each, Spec + Plan sections). **Read `2026-06-02-personal-os-master-plan.md`
  first** — locked cross-arc decisions, migration ledger (0019–0028), shared module template, build
  order, go/no-go gates. Locked: session login in the shell · generic IMAP/SMTP email · Markdown-first
  docs · Google-OAuth read-mirror calendar · "open code" = OpenCode as a gated sandboxed-worktree/
  diff-as-artifact harness. Build order (each shippable; re-validate its plan vs main before building):
  1. `2026-06-02-shell-and-module-framework.md` (+ session login; **builds the template**) — **NEXT**
  2. `tasks.md` · `notes.md` · `operational-surfaces.md` (Memories+Routines UI)
  3. `deep-research.md` + `document-editor.md` (router-backed wow pair)
  4. `recipes.md`   5. `email-client.md` (spike IMAP first)
  6. `calendar.md` (spike `make google-oauth` first)   7. `model-cookbook.md` (closes the router arc)
  8. `code-opencode.md` (spike headless OpenCode first; heaviest Hard-Rule-#1 reconciliation)
  All dated `2026-06-02-` under `docs/specs/`.

### BUILD — branch `feat/personal-os-arc` (NOT merged — operator review pending)
All 10 module **backends + the gateway REST API + the React app shell** are built: **338 py unit
tests + 22 web vitest green, lint + tsc + production build clean**. Modules are usable via chat (run
`jarvis mode semi_autonomous`) AND via the app's **workspace** surface (4th TopBar tab: login →
left nav → 10 panels). Repo round-trips + real-git apply are `@pytest.mark.integration` (run on box).
Backend pattern: `docs/MODULE_TEMPLATE.md`.

**Frontend DONE** (`web/`): `lib/api.ts` (login + module methods; session token = bearer), `LoginGate`
(passphrase; open dev mode just works), `Workspace` + 10 panels (tasks/notes/docs/research/recipes/
calendar/mail/code/models/memories) over `gateway/modules_api.py` (operator-direct CRUD; gated
actions reuse the tools). **REST DONE**: `gateway/deps.py` + `gateway/modules_api.py`.

**DONE (backend, tested, committed):**
- **Shell foundation:** session login (`0019_app_sessions`, `gateway/sessions.py` scrypt+token-hash,
  `/api/login`+`/api/logout`, `_principal` cookie|bearer + static fallback, `make app-passphrase`);
  `tools/grading.py` (Evolution #2 auto-run-vs-gated); `jarvis/modules/` `awareness`+`search` hooks
  + `builtin_tools` registrar (imported by gateway + conversation agent).
- **Tasks** `0020` · **Notes** `0021` · **Documents** `0022` (+versions, `ai.propose_edit` co-write)
  · **Research** `0026` (bounded harness, gated `research.run`) · **Recipes** `0023` (URL import,
  scaler, recipe→shopping-list→tasks) · **Mail** `0024` (cache+triage+compose) · **Calendar** `0025`
  (local truth + Google read-mirror) · **Cookbook** `0027` (per-action backend + presets; wired into
  research+postmortem; `jarvis model prefs|pref|preset`) · **Code/OpenCode** `0028` (sandboxed
  worktree → diff → gated apply; allowlist-only).
- `.env.example`, `MAP.md`, `docs/MODULE_TEMPLATE.md` updated.

**ALSO DONE since:** daily-brief `day_brief` routine action (calendar+tasks+mail+research+homelab,
best-effort) + Routines UI panel (11th) + `/api/routines` + live **mail-sync** code
(`jarvis/mail/sync.py`, run via `jarvis connectors mail-sync`) + `make google-oauth` helper
(`scripts/google_oauth.py`). **Everything buildable-without-creds is now built.**

**ON HOLD — only live config/runs remain (operator provides; assistant drives the box):**
- **Mail:** set `IMAP_HOST/SMTP_HOST` + `MAIL_USERNAME`/`MAIL_PASSWORD` (app password) in box `.env`
  → `jarvis connectors mail-sync` populates the cache+triage (the IMAP spike = confirm it connects).
- **Google Calendar:** create an OAuth client → `make google-oauth` (browser machine) → paste
  `GOOGLE_OAUTH_REFRESH_TOKEN` (+id/secret) into `.env` → `calendar.google.sync()` (live run).
- **OpenCode:** confirm `opencode --version` on the box + set `CODE_REPO_ALLOWLIST`; spike the
  headless command, then replace `code.harness._held_runner` with the real `opencode run` invocation.
- **Login:** `make app-passphrase` → `APP_PASSPHRASE_HASH` in `.env`.

**NOTED FOLLOW-UPS (additive):** Tasks proactive due-nudge worker (reuse reminder poll);
capability-summary labels module write-tools "read-only" (cosmetic); Cmd-K wiring of module search
+ theme presets in the workspace.

**GO-LIVE:** review branch → `make app-passphrase` → merge `feat/personal-os-arc` → on box
`git pull && make deploy` (runs migrations 0019–0028) → set the secrets above → `jarvis mode
semi_autonomous` → use via chat OR the app's **workspace** tab (login → 11 panels). Run mail-sync /
google-oauth / opencode spike to light up the three live integrations.

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
- **[5 DONE] Native mobile app (Capacitor).** Same React console wrapped as an Android app (one
  codebase, orb intact) — `web/android/` committed, build runbook in `docs/MOBILE.md`. Enablers:
  gateway **CORS** (`gateway_cors_origins`, allows capacitor/localhost origins) + a runtime-configurable
  **gateway URL + token** (⚙ Connection settings / Cmd-K, `getGatewayUrl`/`VITE_GATEWAY_URL`) so the
  bundled app reaches the box over Tailscale/NPM; `wsUrl()` derives ws(s) from that base. Native shell
  (`lib/native.ts`, guarded to native): status bar, splash, Android back-button, keyboard→`--kb` var;
  safe-area helpers (`.pt-safe`/`.pb-safe`) on the top bar + composer. Notifications stay on ntfy.
  Build verified (tsc/vite/vitest 17, `cap add android` + sync OK); APK build is the operator's
  Android-Studio step.
- Model: operator moving `MODEL_REASONING` → `qwen3:4b` (lifts recall/triage/extraction fidelity).
- **[deps DONE] Everything on latest.** Capacitor 6→8 (compileSdk 36, Gradle 8.14, JDK 21; android
  regenerated). Front-end: React 18→19, @react-three/fiber 8→9, three 0.184, framer-motion 12,
  Vite 5→8 (Rolldown), Vitest 4, TypeScript 6, Tailwind 3→4 (`@import`+`@config`, `@tailwindcss/
  postcss`). tsc/build/vitest 17 green, custom theme verified in built CSS, console redeployed +
  serving. ⚠ orb (R3F 9) + Tailwind-4 styling are build-verified only — eyeball on device.
- **[security review DONE]** Full-codebase pass fixed: SSRF via redirect/scheme bypass in the egress
  guard (HIGH — redirects now re-validated, http(s)-only), timing-unsafe gateway token compare
  (→ hmac.compare_digest), plugins able to shadow built-in capabilities (load_plugins refuses
  name collisions), WS chat crashing on inference/DB error (now degrades), latent embed-iframe XSS +
  unsafe sandbox (scheme-guarded URLs, dropped allow-same-origin). Reviewed clean: SQL (parameterized),
  SSH (shlex.quote+path validation), webhook HMAC, the execution gate, markdown (React-escaped),
  query caps, div-by-zero guards. SSRF guards verified live on the box.

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
