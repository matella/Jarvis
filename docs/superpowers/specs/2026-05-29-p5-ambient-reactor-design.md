# Phase 5 — Ambient Reactor (design spec)

> Date: 2026-05-29 · Phase 5 (ambient), first slice. Closes the cognition loop: Jarvis acts on
> its OWN perception — a qualifying event auto-runs one cognition step (the infra agent proposes
> a GATED intent). Everything still flows through the M4 approval+mode gate; nothing auto-executes.

## Safety (autonomy starts here — keep it bounded)
- **Observe-only**: the reactor proposes; it NEVER executes. Same gate as M4 (approval + mode);
  under observe the proposed intent just sits awaiting approval.
- **One-shot** per trigger (Hard Rule 2 — no recursive planning); inference is semaphore-serialized.
- **Loop-prevention**: react only to operational events (`source ∈ {docker, metrics}`), never
  Jarvis's own (`intent.proposed`, `incident.*`, `model.*`, `execution.*`) — so proposing can't
  trigger more proposing.
- **Per-entity cooldown** + an **off-switch** (`reactor_enabled`).

## Trigger policy
React on `container.died` / `container.oom_killed` from operational sources → `propose_intent(entity)`.

## Components
- **`core/reactor.py`** — `should_react(event)` (source ∈ operational ∧ type ∈ {died, oom_killed}),
  `ReactorState` (per-entity cooldown), `process_batch(r, ...)` (XREADGROUP → react via
  `propose_intent` → XACK every msg), `run_reactor(once=…)` (group at `$`, no-op if disabled).
- **`core/supervisor.py`** — add `reactor` as the 7th `jarvis run` worker.
- **config**: `reactor_enabled=True`, `reactor_group="jarvis:reactor"`, `reactor_cooldown_s=600`.
- **CLI**: `jarvis reactor run [--once]`.

## Testing → acceptance
- **Unit**: `should_react` (died/oom from docker → yes; intent.proposed from infrastructure_agent
  → no (loop guard); started/info → no; died from a meta source → no); cooldown; supervisor
  registry includes `reactor`.
- **Integration** (Redis, `propose_intent` mocked to avoid real inference): publish a
  `container.died` (operational) + a non-trigger to an isolated stream → `process_batch` reacts
  once on the death, not the other, both acked.
- **Live**: pre-create the reactor group; seed a `container.died` (event row + stream) for a probe
  entity → `jarvis reactor run --once` → an intent is auto-proposed (status=proposed,
  requires_approval); `jarvis intents list` shows it. Nothing executes. Cleaned up.

## Deferred (rest of Phase 5)
auto-correlation; predictive observability (trend forecasting); adaptive attention (learn what
matters); operational playbooks (procedural memory); full operational-mode state machine.

## Process note
Lightweight path (saved preference): this spec is the record; subagent review loop + separate
writing-plans pass skipped. Implementation proceeds directly.
