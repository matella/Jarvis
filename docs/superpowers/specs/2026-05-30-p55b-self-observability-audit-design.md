# Phase 5.5b — Self-observability + Audit — detailed spec

> Date: 2026-05-30 · Hardening foundation, milestone 2. "Jarvis watches Jarvis," and every human
> action is attributable.

## Decisions
- **Self-observability** ships as a `jarvis self` CLI + `jarvis.health` events now; the HTTP
  `/health` endpoint lands with the gateway (6a). Worker liveness via heartbeats.
- **Audit** is a dedicated `audit_log` table (migration 0010) — query-friendly, separate from the
  event spine. Actor = origin string now (`cli` / `reactor` / `<worker>` / `system`); real user
  identity arrives with gateway auth (6a) and slots into the same `actor` column.

## Schema — migration 0010
`audit_log(id, ts, actor, action, target, details jsonb)` + index on ts. (`worker_heartbeats`
can be a small table OR in-memory in the supervisor exposed via `self`; prefer a tiny
`worker_heartbeats(worker PK, last_tick, last_status)` so `self` works across processes.)

## Components
- **`ops/selfcheck.py`** — `health()` gathers: worker liveness (from `worker_heartbeats`), DLQ
  depth (`xlen jarvis:dlq`), stream lag (`xinfo groups`), recent inference latency + swap freq
  (from `inference.completed`/`model.*` events), DB/Redis/Ollama reachability (reuse healthcheck).
  Emits a periodic `jarvis.health` event (degraded → warning). `jarvis self` renders it.
- **supervisor** — each worker writes a heartbeat each loop (`worker_heartbeats` upsert); a stale
  heartbeat surfaces as a degraded worker in `self`.
- **`audit/log.py`** — `record(conn, actor, action, target, **details)`; called by
  `service.approve/reject/execute`, `modes.set_mode`, the reactor/agents (actor=their origin), and
  chat actions (6a, actor=the user). `jarvis audit [--since]` lists the timeline.
- **CLI:** `jarvis self`, `jarvis audit`.

## Testing → acceptance
- **Unit:** `health()` assembly from injected counters; audit `record` row shape; stale-heartbeat
  → degraded.
- **Integration:** an approve/reject/mode-set writes an `audit_log` row with the right actor +
  target; `self` reports DLQ/lag/reachability against the live tunnel.
- **Live:** `jarvis self` shows all workers green + DLQ 0 + inference latency; approve an intent →
  `jarvis audit` shows it with actor; kill a worker → `self` flags it degraded.

## Dependencies / notes
Audit `actor` is coarse until 6a adds identities. `/health` HTTP is 6a (needs the gateway). No new
infra.
