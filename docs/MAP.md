# MAP — module index

Look here to find where something lives before scanning the tree. Entry points are the
file you open first when working in that module; they are aspirational until the module's
milestone (right column) is built. A module gets its own nested `CLAUDE.md` only once it
has rules worth lazy-loading — created with the module, not in advance.

| Module (`jarvis/…`) | Purpose | Entry point | Built in |
|---|---|---|---|
| `intents/` | Intent + Execution contracts (Pydantic, schema-versioned, causal ids) + approval/mode gate | `models.py`, `service.py` | M1, M4 |
| `incidents/` | Correlated-alert incident contract + repository (alert correlation output) | `models.py` | P2 |
| `playbooks/` | Operator-authored procedural memory (pgvector); grounds agent proposals | `repository.py` | P5 |
| `state/` | Postgres state models + the event→state **projector**, snapshots | `projector.py` | M2 |
| `migrations/` (repo root) | Alembic versioned schema migrations (runner-only, raw SQL) | `versions/0001_initial_schema.py` | M1 |
| `memory/` | `MemoryStore` (pgvector) + **governance** (list/forget/consolidate) | `store.py`, `governance.py` | M1, X-D |
| `events/` | Redis Streams producers/consumers, event schemas, DLQ handling | `consumer.py` | M2 |
| `ingest/` | Docker events (M2); metrics (P2); topology (P2); code indexer (P3); predict (P5); **Prometheus scrape + Loki spikes** (cross-cut C) | `docker_events.py`, `metrics.py`, `prometheus.py`, `loki.py` | M2–P5, X-C |
| `routines/` | Scheduled proactive briefings (cron-ish over existing capabilities) | `scheduler.py` | X-A |
| `eval/` | Replay-based regression harness (re-run stored contexts, flag decision drift) | `harness.py` | X-B |
| `feedback.py` | Operator 👍/👎 → feedback rows + events (adaptive-attention signal) | `feedback.py` | X-B |
| `cli/` | Terminal client + introspection (`tail`, `inspect`, `trace`, `explain`, `replay`) | `main.py` | M2, M4 |
| `models/` | Ollama client, model-router policy, inference semaphore + timing events; **GPU scheduler** (priority queue, swap limiter, budgets) | `router.py`, `scheduler.py` | M3, P11 |
| `core/` | Orchestrator: assembly (M3), context store (M4), journal (P2), supervisor + ambient reactor + mode state machine (P5); **planner + plan_executor + policies** (P7) | `assembly.py`, `reactor.py`, `modes.py`, `planner.py`, `plan_executor.py` | M3–P7 |
| `agents/` | One-shot reasoning endpoints (summarizer, infrastructure agent, alert correlator, coder Q&A); **conversation/executive agent** (P6a) | `summarizer.py`, `conversation.py` | M3–P6 |
| `tools/` | Deterministic, capability-scoped executors (the tool contract; `preview`/`revert` added P7) | `registry.py` | M4, P7 |
| `notify/` | Contextual notifications: rules-based notifier consumer + webhook channel | `notifier.py` | Phase 4 |
| `gateway/` | FastAPI + WebSocket API: chat `/ws` (+ voice audio), REST reads, presence feed, inbound webhooks, auth | `app.py`, `webhooks.py` | P6a, P8, P10 |
| `conversation/` | Chat session/turn store (memory window) for the gateway | `store.py` | P6a |
| `security/` | Secrets provider, egress allowlist, sanitize + untrusted framing (kill switch) | `egress.py`, `sanitize.py`, `secrets.py` | P5.5c |
| `orchestration/` | Plan + PlanStep records + repository (multi-step goals; executor lives in `core/`) | `models.py` | P7 |
| `connectors/` | External read (feeds RSS, mail IMAP → events) + act-Tools (mail.send, ha.set_state) | `base.py`, `feeds.py`, `mail.py` | P8 |
| `search/` | SearchProvider (SearXNG) + web RAG + Playwright capture; egress-guarded, sanitized | `searxng.py`, `rag.py` | P9 |
| `voice/` | STT (Whisper.cpp), TTS (Piper), wake gate — transport over the conversation pipeline | `stt.py`, `tts.py`, `wake.py` | P10 |
| `ops/` | Durability (backups + DR drill) + self-observability (`jarvis self`/health) | `backup.py`, `health.py` | P5.5a/b |
| `audit/` | Append-only audit log (who did what) | `log.py` | P5.5b |
| `web/` (repo root) | React + Vite console: presence orb (WebGL) + HUD, artifact renderers, voice/audio-reactive orb | `web/src/App.tsx` | P6b, P10 |

## Where the truth lives
- **What to build next:** `docs/STATUS.md`
- **Build order + acceptance tests:** `docs/PLAN.md`
- **Rules that must never bend + record/contract invariants:** `CLAUDE.md`
- **Why a choice was made (before reopening it):** `docs/DECISIONS.md`
- **Full architecture rationale + long-term phases:** `docs/ARCHITECTURE.md`
