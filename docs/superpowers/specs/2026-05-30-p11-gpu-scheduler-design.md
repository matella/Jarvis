# Phase 11 — GPU scheduler + cognition budgets — detailed spec

> Date: 2026-05-30 · Generalize the global inference semaphore into a real scheduler once
> chat + plans + reactor + connectors + routines compete for the one 8 GB card. (DECISIONS deferred
> this until contention existed; orchestration + chat create it.)

## Decisions
- A **priority queue** in front of inference replaces the bare `Semaphore(1)`: one model resident,
  requests scheduled by **priority** (interactive chat/voice > plan steps > background
  reactor/summaries/correlation), with **swap-frequency limits** (don't thrash models) and
  **per-session/routine token+time budgets** (a runaway routine can't starve the GPU).

## Components
- **`models/scheduler.py`** — wraps `router.chat/embed/embed_many`: each call submits a
  `Request(role, priority, budget, correlation_id)` to the scheduler; the scheduler serializes to
  one in-flight, prefers higher priority, **batches same-model requests** to cut swaps, and enforces
  swap-frequency + budget caps. Emits `inference.scheduled`/`inference.completed` (extend existing)
  with wait-time + queue-depth for observability.
- **budgets:** per-session (chat), per-routine, per-plan token/time budgets (config defaults); a
  request over budget is rejected/deferred (surfaced to the caller).
- **router** keeps its role→tag + one-resident + model.* events; the scheduler owns ordering.
- **config:** priorities, max swaps/min, budget defaults.

## Testing → acceptance
- **Unit:** ordering (high-priority preempts queued low); swap-frequency limiter; budget rejection;
  same-model batching reduces swaps (with a fake clock/model).
- **Integration:** concurrent submissions (interactive + background) → interactive served first,
  one-resident invariant holds, swaps bounded.
- **Live:** drive chat while the reactor + a plan run → chat stays responsive, `model.loaded`
  frequency stays under the cap, a capped routine can't exhaust the GPU; visible via the events.

## Dependencies
Slot in as soon as concurrent inference bites (likely during Phase 7 or after 6b). Builds on the
M3 router + semaphore + timing telemetry (the deferred "telemetry first" seed).
