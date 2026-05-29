# Phase 4 — Contextual Notifications (design spec)

> Date: 2026-05-29 · Phase 4. The feasible+valuable Phase-4 slice for a single-box homelab.
> (Execution nodes / capability manifests / cross-device deferred — premature with one node,
> per the project's anti-premature-architecture discipline.)

## Decision
A deterministic **notifier consumer** on the event spine (a second consumer group, per M2's
design) filters notify-worthy events and pushes them to a webhook. No LLM. Runs as a `jarvis run`
worker (the 6th collector).

## Triggers (attention fatigue is the enemy)
- `incident.correlated` events (the deduped high-signal aggregate), and
- individual **critical**-severity events (e.g. `container.oom_killed`).
Per-`(type, entity)` cooldown to avoid storms.

## Channel — generic webhook
`POST` JSON `{title, message, priority, event_type, entity, severity, ts}` to
`NOTIFY_WEBHOOK_URL`. Unset → log-only no-op. Dependency-light (urllib). Send is best-effort
(never crashes the notifier).

## Components
- **`notify/channel.py`** — `send(title, message, priority, **fields)`: POST JSON to the
  webhook (or log if unset); swallow errors.
- **`notify/notifier.py`** — `should_notify(event)`, `_format(event) → (title, message, priority)`,
  `NotifierState` (per-key cooldown), `process_batch(r, ...)` (XREADGROUP → filter → send → XACK
  every message), `run_notifier(once=…)`.
- **`events/stream.ensure_group`** gains a `start_id` param: notifier group starts at `$`
  (only NEW events — don't page about historical incidents on first start); projector stays `0`.
- **`core/supervisor.py`** — add `notify` worker (`run_notifier`).
- **config**: `notify_webhook_url=""`, `notify_group="jarvis:notifier"`, `notify_cooldown_s=300`.
- **CLI**: `jarvis notify run [--once]`, `jarvis notify test` (send a test notification).

## Testing → acceptance
- **Unit**: `should_notify` (critical→yes, incident.correlated→yes, warning/info→no);
  `_format`; `NotifierState.allow` cooldown; `channel.send` log-only when no URL.
- **Integration** (Redis): publish a critical event to an isolated test stream/group →
  `process_batch` notifies once + acks (pending 0); a non-critical event → acked, not notified
  (send monkeypatched to capture).
- **Live**: a local capture HTTP server as `NOTIFY_WEBHOOK_URL`; publish a `container.oom_killed`
  → `notify run --once` → the receiver gets the JSON. Cleaned up after.

## Deferred (Phase 4 proper, when a 2nd node exists)
execution nodes, capability manifests, cross-device action routing.

## Process note
Lightweight path (saved preference): this spec is the record; subagent review loop + separate
writing-plans pass skipped. Implementation proceeds directly.
