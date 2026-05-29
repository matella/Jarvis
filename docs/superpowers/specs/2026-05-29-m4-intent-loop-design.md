# M4 — Intent Loop, read-only first (design spec)

> Date: 2026-05-29 · Milestone: **M4** (see `docs/PLAN.md`). The deterministic execution
> boundary becomes real code: `LLM → IntentProposal → validate → Intent → approval+mode gate
> → capability-scoped executor → Execution`. Default mode `observe` = propose-only.

## Acceptance test (from PLAN.md)
Agent proposes a `restart_container` intent with confidence/risk/reversible; the
`requires_approval` gate works under `observe`; the action is recorded as a **separate
`executions` row sharing the intent's `correlation_id`**; `jarvis explain` surfaces the exact
stored context that produced the decision.

## Decisions
- **Dedicated `contexts` table** (migration 0002) stores assembled prompt + model/params,
  keyed by `context_ref`. `explain`/`replay` read it.
- **Dry-run under observe; real execution needs mode elevation.** Approval is independent of
  mode. Once approved: `observe` → dry-run (`executions` row `outcome=skipped`, before_state
  captured, no infra touched); elevated mode → real executor.
- **Agent output is JSON-constrained** (`format=json`) → `IntentProposal` Pydantic →
  capability validation. Unknown/invalid proposals are rejected, never executed.

## Schema — migration 0002
`contexts(context_ref PK, prompt text, model text, params jsonb, created_at)`,
insert `ON CONFLICT DO NOTHING` (reused context dedups).

## Components (MAP.md seams)
- **`core/context_store.py`** — `ContextRecord`; `save_context` / `get_context`.
- **`tools/contract.py`** — frozen tool contract: `Tool {name, version, permissions[],
  side_effects, idempotent, max_retries, timeout_seconds, rollback(none|manual|automatic)}`
  + `run`/`inspect` callables; `ToolResult`.
- **`tools/registry.py`** — `register`/`get_tool`/`capabilities`; ships
  `docker.restart_container` (side_effects=true, idempotent=false, rollback=none, timeout=30s):
  capability-scoped subprocess `docker --context … restart`, `inspect` via `docker inspect`.
- **`agents/infrastructure.py`** — `IntentProposal {type, target, summary, confidence, risk,
  reversible}`; one-shot `propose_intent(entity)`: pick trigger event → assemble context →
  `save_context` → `router.chat(reasoning, format=json)` → parse+validate (type ∈ capabilities
  ∪ advisory, confidence clamped) → build `Intent` (adopts the **trigger event's
  `correlation_id`**, `causation_id`=trigger id; `requires_approval`=tool.side_effects or
  risk==high) → `insert_intent` → emit `intent.proposed`. Exposes `_messages`/`_parse` so
  `replay` reuses them.
- **`intents/service.py`** — `approve` / `reject` / `execute`. Gate: `requires_approval` and
  not `approved` → `ApprovalRequired` (no row). Then mode: `observe` → dry-run skipped row;
  elevated → real `tool.run` (timeout enforced; typed `failure_class` on error). Always an
  `executions` row sharing `correlation_id`, `causation_id`=intent id; intent →
  executed/failed (skipped leaves it approved). Emits `execution.recorded`.
- **`models/router.py` + `client.py`** — add `format` passthrough for JSON-constrained chat.
- **CLI** — `jarvis intents propose <entity> | list | approve <id> | reject <id> |
  execute <id>`; `jarvis inspect intent <id>`; `jarvis explain <id>` (stored prompt+params);
  `jarvis replay intent <id>` (re-run model on stored context, diff vs original, note
  nondeterminism).

## Event types added (best-effort spine telemetry)
`intent.proposed` (entity=`intent:<id>`) · `intent.approved` · `execution.recorded`
(payload: outcome, failure_class). Intents/executions themselves are written directly to
Postgres by the service (deterministic orchestrator writes), not ingested from Redis; `trace`
reads all three tables by `correlation_id`.

## Testing → acceptance
- **Unit** (no model/DB): `IntentProposal` parse/validate (good JSON, unknown type rejected,
  confidence clamped); tool contract + registry lookup; gate logic with a fake tool —
  ApprovalRequired when unapproved; dry-run skipped under observe; real run under elevated mode
  (executor mocked); failure → typed `failure_class`.
- **Integration** (DB + Ollama via tunnel): `propose_intent` against seeded events returns a
  validated Intent with a stored `context_ref`; `get_context` round-trips; full
  propose→approve→execute (elevated, fake/real tool) writes a linked execution sharing the
  correlation_id. Skips if model/DB unavailable.
- **Live acceptance**: throwaway `jarvis-m4-probe`, stop it → ingest+consume → `intents propose`
  → gate demo (observe dry-run vs `JARVIS_MODE=assist` real restart) → `explain` / `replay` /
  `trace` showing event→intent→execution.

## Process note
Lightweight path (saved preference): this spec is the record; subagent review loop + separate
writing-plans pass skipped. Implementation proceeds directly.
