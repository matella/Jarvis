# Jarvis — Build Plan

Companion to `CLAUDE.md`. This is the **execution order**. Work it top-down; each
milestone has an acceptance test that must pass before moving on. Do not build agents,
memory ranking, or planning before the spine (M0–M3) is visible and tested.

---

## Guiding frame

The bottleneck is orchestration efficiency, not model intelligence. Build the
event-driven cognition spine first; everything else is additive.

**The MVP spine:**

```
Docker events → Redis Stream → Jarvis Core → Postgres (state projection + pgvector)
              → LLM summarization → Terminal UI
```

If the spine works, the rest evolves naturally. If it fails, nothing downstream matters.
De-risking order: prove the deterministic plumbing end-to-end with **zero AI**, then add
the model as a late step — the model is the part most likely to work in isolation; the
plumbing is where the bugs hide.

---

## Data model (build this first — these are the most important objects)

PostgreSQL + pgvector, one database. All boundary rows carry `schema_version`,
`correlation_id`, and `causation_id`.

| Table | Role | Key fields |
|---|---|---|
| `events` | Append-only **source of truth** | `id`, `type`, `severity`, `source`, `entity_ref`, `occurred_at`, `recorded_at`, `payload jsonb`, `correlation_id`, `causation_id`, `schema_version` |
| `intents` | Model **proposals** | `intent_id`, `created_at`, `type`, `target jsonb`, `reasoning jsonb` `{summary, confidence, risk, reversible}`, `requested_by`, `context_ref`, `requires_approval`, `status`, `correlation_id`, `causation_id`, `schema_version` |
| `executions` | Deterministic **actions** taken for an intent | `exec_id`, `intent_id` (fk), `created_at`, `attempt`, `outcome`, `before_state jsonb`, `after_state jsonb`, `error`, `failure_class`, `correlation_id`, `causation_id`, `schema_version` |
| `state` | Current operational state — **projection of `events`** | `entity`, `kind`, `status`, `attrs jsonb`, `updated_at`, `last_event_id`. Written **only** by the projector |
| `snapshots` | Compaction checkpoints | `id`, `ts`, `kind`, `blob jsonb`, `last_event_id` |
| `memory` | Vector memory behind a `MemoryStore` interface | `id`, `kind`, `content`, `embedding vector`, `metadata jsonb`, `ts` |

### Cross-cutting contract rules (fixed at M1)

- **Causal identity.** `correlation_id` groups a whole causal chain; `causation_id` is the
  parent pointer to the immediate cause. Every event/intent/execution sets both.
- **Time semantics.** Events carry `occurred_at` (world time) and `recorded_at` (ingest
  time). Intents/executions use `created_at`.
- **Event naming + severity.** `type` is `entity.verb` past-tense (`container.oom_killed`);
  `severity ∈ {debug, info, warning, error, critical}`.
- **Failure classes.** `failure_class ∈ {permission_denied, timeout, network_failure,
  resource_exhaustion, validation_failure, tool_unavailable, unknown}` — used by the DLQ
  (M2) and execution errors (M4).
- **Intent ≠ Execution.** One Intent → zero-or-more Executions (proposed → approved/rejected
  → executed → failed → retried). Never flatten them.
- **`context_ref`** on every Intent links to the exact assembled context + model
  name/version/params that produced it. This is the answer to "why?".
- Pydantic models for Intent and Execution are the canonical definitions; the DDL follows
  them.

**Reference Intent envelope:**

```json
{
  "intent_id": "uuid",
  "schema_version": 1,
  "correlation_id": "corr_<uuid>",
  "causation_id": "evt_<uuid>",
  "type": "docker.restart_container",
  "target": { "container": "nginx" },
  "reasoning": {
    "summary": "Container unhealthy after repeated failures",
    "confidence": 0.91,
    "risk": "low",
    "reversible": true
  },
  "requested_by": "infrastructure_agent",
  "context_ref": "ctx_<hash>",
  "requires_approval": false,
  "status": "proposed",
  "created_at": "2026-05-29T13:00:00Z"
}
```

---

## Milestones

### M0 — Repo + infra skeleton
- `docker-compose.yml` (Postgres+pgvector, Redis), `pyproject.toml`, config loading,
  `.env.example`, this plan + `CLAUDE.md` in place.
- **Acceptance:** `docker compose up` brings up Postgres and Redis; a healthcheck script
  connects to both and exits 0.

### M1 — Data model & contracts
- DDL + migrations for `events`, `intents`, `executions`, `state`, `snapshots`, `memory`,
  including `correlation_id`/`causation_id`, `occurred_at`/`recorded_at`, `severity`, and
  the `failure_class` enum.
- Pydantic `Intent` and `Execution` models with `schema_version`.
- `MemoryStore` interface with a pgvector implementation.
- **Acceptance:** can insert and query an event, an intent, and a linked execution sharing
  a `correlation_id`; round-trip an embedding through `MemoryStore` and retrieve by
  similarity.

### M2 — Event spine, zero AI
- Docker events ingester → Redis Stream → **consumer group** → `events` table → state
  **projector** updating the `state` projection.
- **Dead-letter path:** events that fail processing go to a `jarvis:dlq` stream tagged with
  `failure_class` and error, replayable later. (Use the consumer-group pending list +
  `XCLAIM`/`XAUTOCLAIM`.)
- **Introspection CLI (the payoff of the schema):**
  `jarvis events tail`, `jarvis state show`, `jarvis inspect event <id>`,
  `jarvis trace <correlation_id>`, `jarvis dlq`.
- **Acceptance:** restart a real container; the lifecycle event flows end-to-end, appears
  in `jarvis events tail`, updates `state`, and `jarvis trace` shows the causal chain.
  **No model is involved yet.**

### M3 — Add the model
- Ollama client + model-router policy (default → Qwen 3.5 9B; coding tasks → Coder 7B),
  behind a **global inference semaphore (concurrency = 1)**.
- Emit `model.loaded` / `model.unloaded` / `inference.completed` events with timings, so
  swap frequency and latency are observable (the seed for any future scheduling).
- Deterministic context assembly: recency + entity match + vector relevance, token-budgeted
  to ≤ 8K. The LLM only *compresses/summarizes* the assembled context — it never chooses
  what to retrieve.
- One-shot **summarizer** agent over recent infra events.
- **Acceptance:** `jarvis summarize --since 12h` →
  *"3 containers restarted overnight from OOM pressure…"* grounded in real `events`;
  `inference.completed` events show per-call timing.

### M4 — Intent loop (read-only first)
- Infrastructure agent proposes Intents (investigate / recommend), validated against schema
  + capabilities, logged with `context_ref` and causal ids.
- **Tool contract** implemented (version, permissions, side_effects, `idempotent`,
  `max_retries`, `timeout_seconds`, `rollback`); executors are capability-scoped and emit
  typed `failure_class` on error.
- **Operational mode** seed: a single global `mode`, default `observe` (propose-only). The
  approval gate is mode-aware. The full mode state machine stays deferred.
- Execution layer handles low-risk, reversible actions behind the approval gate.
- **Introspection CLI:** `jarvis inspect intent <id>`, `jarvis explain <intent_id>`
  (shows the stored context that produced it), `jarvis replay intent <id>` (re-assembles
  context and re-runs the model, diffing output — explicitly noting nondeterminism).
- **Acceptance:** agent proposes a `restart_container` intent with confidence/risk/reversible;
  `requires_approval` gate works under `observe` mode; the action is recorded as a separate
  `executions` row sharing the intent's `correlation_id`; `jarvis explain` surfaces the
  exact context that produced the decision.

---

## Deferred — seed now, build later

- **GPU scheduling / resource budgets.** Now: serialize inference + emit timing telemetry
  (M3). Later (Phase 2, when summaries and coding compete): treat GPU time as a schedulable
  resource with VRAM/context/token budgets and swap-frequency limits.
- **Operational modes.** Now: `observe` as the default safety posture (M4). Later:
  `assist`, `approval_required`, `semi_autonomous`, `maintenance_mode`.

---

## Later phases (see `docs/ARCHITECTURE.md` for detail)

- **Phase 2 — Operational intelligence:** metrics ingest (cAdvisor / `docker stats` for
  CPU/mem/GPU trends, which are *not* in the Docker events stream), alert correlation,
  topology awareness, operational journaling, GPU scheduling.
- **Phase 3 — Development intelligence:** coding agent, repository indexing, CI awareness,
  deployment analysis.
- **Phase 4 — Distributed execution:** execution nodes, capability manifests, cross-device
  actions, contextual notifications.
- **Phase 5 — Ambient intelligence:** proactive assistance, predictive observability,
  adaptive attention, operational playbooks, full operational modes.
- **Phases 5.5–11 — Conversational orchestrator** (planned; full spec:
  `docs/superpowers/specs/2026-05-29-conversational-orchestrator-program.md`):
  - **5.5 Hardening foundation** (first): backups+DR, event compaction/retention,
    self-observability, audit log + actor attribution, PII redaction, security primitives
    (vault, egress allowlist, prompt-injection quarantine, kill switch).
  - **6** gateway + React console + conversation/executive agent (talk to Jarvis) + self-describing
    capabilities + decision inspector · **7** planner + deterministic plan executor + action safety
    (rollback, blast-radius/rate limits, approval policies, what-if) · **8** connectors
    (mail/calendar/feeds/Home Assistant, read+act gated) + inbound webhooks · **9** real-time
    search (SearXNG) · **10** voice (Whisper/Piper) · **11** GPU scheduler + cognition budgets.
  - **Cross-cutting:** scheduled routines/briefings · feedback loop + eval/replay harness · richer
    observability ingest (Prometheus/Loki) · memory governance.
  Additive; same deterministic-boundary / observe-by-default / replay / local-first rules.

---

## Out of scope until the spine is proven

Qdrant · Neo4j / knowledge graph · NATS · multi-service split · multi-turn or recursive
agents · voice pipeline · GPU scheduler · full operational-mode state machine. Each is a
deliberate *later* decision, not an oversight.
