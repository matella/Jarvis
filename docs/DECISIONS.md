# DECISIONS

Terse log of locked choices. Read before reopening any of them. Format: **decision —
why — rejected alternative**. Append new ones; don't rewrite history (mark superseded).

## Principles
- **Deterministic execution boundary.** LLMs reason; deterministic code acts. Everything
  flows `LLM → Intent → validation → executor`. *Why:* safety, auditability, reproducibility.
- **Event-driven + state-centric, not conversation-centric.** *Why:* the product is
  operational cognition, not chat.
- **Plumbing before AI; observability before autonomy.** *Why:* the LLM is the easy part;
  event topology, state consistency, and replay are the hard part and where bugs hide.

## Storage & infrastructure
- **Postgres + pgvector for state *and* memory.** *Why:* early scale is tiny (tens of
  thousands of vectors); one database = fewer containers, backups, auth systems, and
  simpler transactions. *Rejected (for now):* Qdrant — earns its place only at larger scale
  or for advanced payload filtering; kept behind a `MemoryStore` interface so the swap is cheap.
- **Redis Streams for the event bus.** *Why:* consumer groups, pending-list/DLQ, `MAXLEN`
  capping, and `XRANGE` replay cover the requirements. *Rejected (for now):* NATS — revisit
  only if multi-node throughput demands it.
- **No knowledge graph yet.** *Why:* events + embeddings + relational state are enough for a
  long time. *Rejected (for now):* Neo4j / ontology engine — classic premature-architecture trap.

## Models & serving
- **Ollama is the runtime; the "model router" is a thin policy layer over it.** *Why:* Ollama
  already does GGUF serving, an OpenAI-compatible API, and auto load/unload + `keep_alive`.
  *Rejected:* vLLM — wants the model resident and doesn't swap gracefully on a single 8GB card.
- **Qwen 3.5 9B (Q4_K_M, ~6.6 GB) is the warm default** (reasoning, summaries, intent);
  **Qwen 2.5-Coder 7B** swaps in only for coding. *Why:* 9B is the 2026 consensus best fit
  for 8GB with room for context. *Rejected:* 14B — won't co-reside with KV cache on 8GB and
  goes CPU-bound; revisit only on a real quality ceiling.
- **The router/classifier is NOT an LLM** — rules + embedding similarity on CPU. *Why:*
  faster, and frees the GPU.
- **Embeddings: nomic-embed-text on CPU.** Voice (Whisper.cpp + Piper) also CPU. *Why:* keep
  everything non-LLM off the GPU so nothing competes for VRAM.
- **One LLM resident at a time; ≤8K interactive context; Q4_K_M, never lower; inference
  serialized via a global semaphore.** *Why:* 8GB Turing card, ~3–5 s swap cost. The
  bottleneck is orchestration efficiency, not model intelligence.

## Cognition & contracts
- **Agents are one-shot ("AI-enhanced functions"), never multi-turn or recursive.** *Why:*
  every extra inference/swap costs seconds; multi-turn loops thrash the GPU and explode tokens.
- **Event log is the source of truth; `state` is a projection of it; snapshots are
  compaction checkpoints (change-triggered + heartbeat).** *Why:* replayability,
  recoverability, no state drift. Only the projector writes `state`.
- **Intent ≠ Execution — separate records, one Intent → many Executions.** *Why:* enables
  approvals, retries, dry-runs, and honest audit (an intent can be proposed, rejected,
  executed, fail, retry).
- **Replay = log the model's I/O + `context_ref`, never re-run the model.** *Why:* inference
  is non-deterministic across sampling/batching/versions; "why did it decide this?" is
  answered by the recorded inputs.
- **`schema_version` on every boundary record; migrate forward, never break old rows.**
  *Why:* replay-across-time breaks the moment the schema changes silently.
- **`correlation_id` (chain) + `causation_id` (parent pointer) on every record.** `trace_id`
  is a log/span concept only — not a third id on data rows. *Why:* causal debugging;
  unrecoverable for historical data if added late.
- **Events carry `occurred_at` (world time) + `recorded_at` (ingest time).** *Why:*
  event-time is unrecoverable if collapsed into one field.
- **Event `type` = `entity.verb` past-tense; `severity ∈ {debug,info,warning,error,critical}`.**
  *Why:* renaming types across a historical log is the expensive failure mode.
- **`failure_class ∈ {permission_denied, timeout, network_failure, resource_exhaustion,
  validation_failure, tool_unavailable, unknown}`.** *Why:* typed failures drive retries and
  operational reasoning.
- **Tool contract (built M4):** every tool declares `version`, `permissions`, `side_effects`,
  `idempotent`, `max_retries`, `timeout_seconds`, `rollback` (`none|manual|automatic`).
  *Why:* replay/retry are unsafe without idempotency + timeout + retry policy declared.
- **DLQ via Redis consumer-group pending list (`XCLAIM`/`XAUTOCLAIM`) → `jarvis:dlq` stream.**
  *Why:* silent processing failures destroy trust.

## Deferred — seed now, build later
- **GPU scheduling / resource budgets.** Now: serialize inference + emit timing telemetry.
  Later (Phase 2): GPU time as a schedulable resource. *Why deferred:* only one inference path
  exists today — nothing to schedule yet; building it now would violate scope discipline.
- **Operational modes.** ~~Now: a single global `mode`, default `observe`.~~ **BUILT (P5)**:
  a persisted, runtime-settable state machine (`core/modes.py`) — `observe` (dry-run) /
  `approval_required` (real, human-approved) / `semi_autonomous` (auto-approve+run low-risk
  reversible, else require approval) / `maintenance` (freeze). One `decide(mode, intent)` policy
  governs the execution gate AND the ambient reactor. Dropped `assist` (overlapped
  approval_required); `maintenance_mode` → `maintenance`.
