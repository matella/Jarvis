# Phase 7 — Full orchestration + action safety — detailed spec

> Date: 2026-05-30 · The "full orchestrator": multi-step goals. Planning is one-shot; coordination
> is deterministic code (Hard Rule 2 intact). Plus the safety needed before autonomy is used hard.

## Decisions
- **Planner = one-shot agent → a validated plan DAG** of *known capabilities* (intent types /
  queries / sub-agent calls). **plan_executor = deterministic code** (not an LLM loop) sequencing
  steps, each through the existing Intent→gate→executor (or a read query).
- **Action safety lands here:** execute the tool contract's `rollback`; blast-radius + rate limits;
  approval policies/delegation (extends modes); plan simulation/what-if.

## Schema — migration 0012
`plans(plan_id, goal, status, steps jsonb, correlation_id, context_ref, created_at)`
(+ `plan_steps` if steps need their own rows for status/retry; start with embedded `steps` +
linking executions by correlation_id).

## Components
- **`core/planner.py`** — `plan(goal) -> Plan`: one-shot (format=json) → ordered/DAG steps, each a
  capability + args; validate every step against the registry (unknown → rejected). Stores the plan
  + `context_ref`.
- **`core/plan_executor.py`** — deterministic: walk steps respecting deps; read steps query; action
  steps → `service.execute` (mode-gated); record per-step outcome; stop/rollback on failure per
  policy. The whole run shares one `correlation_id` (trace shows the full chain).
- **action safety:**
  - **rollback:** tools with `rollback=automatic` get a `revert()`; executor snapshots before
    (via `inspect`) and reverts on failure for reversible steps.
  - **`tools/contract`** gains `preview(target)` (what would change) → powers simulation.
  - **`core/policies.py`** — approval policy eval (auto-approve rules by capability/entity/risk/
    time), composing with `modes.decide`.
  - **limits:** blast-radius (≤K entities/plan) + rate (≤N actions/window) enforced in the gate.
- **CLI/chat:** `jarvis plan "<goal>" [--simulate]`; chat "diagnose & fix …" issues a plan.

## Testing → acceptance
- **Unit:** plan validation (unknown capability rejected); executor sequencing + dep handling +
  failure→rollback (fake tools); policy eval matrix; blast-radius/rate limit enforcement.
- **Integration:** a 2–3 step plan over real capabilities runs step-by-step under observe (all
  dry-run) then assist; a forced reversible-step failure rolls back; one `trace` chain.
- **Live:** "diagnose why a probe is unhealthy and fix it" → simulate → execute gated → trace.

## Dependencies
M4 gate, P5 modes, P5 reactor (can issue plans). Likely first place the GPU scheduler (11) is
needed (a plan fires several inferences).
