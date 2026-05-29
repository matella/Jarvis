# M2 — Event Spine, Zero AI (design spec)

> Date: 2026-05-29 · Milestone: **M2** (see `docs/PLAN.md`). No model is involved anywhere
> in M2 — this is the deterministic plumbing that makes the schema visible.

## Acceptance test (from PLAN.md)
Restart a real container → the lifecycle event flows Docker → Redis Stream → consumer →
`events` table → state **projector** → appears in `jarvis events tail`, updates `state`, and
`jarvis trace <correlation_id>` shows the causal chain. **No model involved.**

## Decisions
- **Docker event source: subprocess** `docker --context jarvis events --filter type=container
  --format {{json .}}`. Zero new deps, reuses the working SSH context. Auto-reconnect on EOF.
- **CLI: Typer + Rich**, registered as a `jarvis` console script.
- **Projector: focused container projector**, written as a pure `(conn, event)` dispatch on
  `event.type` so replay/rebuild reuses it and generalizing later is a one-function change.
- **Resist low-signal events** (CLAUDE.md): the ingester allowlists meaningful actions and
  drops the `exec_*` healthcheck firehose.

## Flow & components (MAP.md seams)
```
docker events ─▶ ingest/docker_events.py ─▶ Redis jarvis:events
                                                  │  (consumer group jarvis:projectors)
                                                  ▼
                                        events/consumer.py
                                   per msg, one DB tx:
                                   insert_event (ON CONFLICT DO NOTHING)
                                   → state/projector.project() → XACK
                                   failure → pending → XAUTOCLAIM retry
                                   → after max_deliveries → jarvis:dlq
```
- **`ingest/docker_events.py`** — `map_event(raw)` (docker JSON → `Event` or None for noise);
  `run_ingester()` streams + publishes. Allowlist: start/restart/die/stop/kill/oom/create/
  destroy/pause/unpause + `health_status: …`. `entity_ref=container:<name>`,
  `occurred_at` from `timeNano`, each ingested event roots a new `correlation_id`.
- **`events/stream.py`** — `get_redis`, `ensure_group`, `publish_event`, `publish_dlq`. Stream
  capped `MAXLEN ~ stream_maxlen`. Message body: `{"data": event.model_dump_json()}`.
- **`events/consumer.py`** — `ConsumerConfig` (names/limits, defaults from settings, overridable
  for tests); `process_new` (XREADGROUP `>`), `process_pending` (XPENDING → XCLAIM retry or
  → DLQ when `times_delivered > max_deliveries`), `run_batch`, `run_forever`.
- **`state/models.py`** — `StateRow` (deferred from M1, lands here).
- **`state/projector.py`** — `project(conn, event)`: container lifecycle → `state` upsert,
  `entity=container:<name>`, `kind=container`. **Monotonic** via ULID-sortable `last_event_id`
  (`ON CONFLICT … WHERE state.last_event_id < EXCLUDED.last_event_id`); attrs merged with `||`;
  `status = COALESCE(EXCLUDED.status, state.status)` so health-only events don't clobber status.
- **`cli/main.py`** — Typer+Rich: `ingest`, `consume`, `events tail`, `state show`,
  `inspect event <id>`, `trace <correlation_id>`, `dlq`. Entry `jarvis = jarvis.cli.main:main`.
- **`events/repository.insert_event`** gains `ON CONFLICT (id) DO NOTHING` (redelivery-safe).

## Event → status map (projector)
`started/restarted/unpaused → running` · `died/stopped/killed → exited` ·
`oom_killed → oom_killed` · `paused → paused` · `created → created` · `destroyed → destroyed` ·
`health_changed → status unchanged, attrs.health set`.

## Config additions
`docker_context=jarvis` · `events_stream=jarvis:events` · `consumer_group=jarvis:projectors` ·
`dlq_stream=jarvis:dlq` · `stream_maxlen=100000` · `max_deliveries=5`.

## Testing → acceptance
- **Unit** (no DB/Redis): `map_event` for start/die(+exit_code)/oom/health/`exec_*`-dropped/
  non-container; projector status mapping; Event JSON round-trip.
- **Integration** (DB+Redis via tunnel, isolated **per-test stream/group** names, deleted after):
  publish→`run_batch`→assert event row + state row (`running`) + pending empty;
  poison message (`data="not-json"`) with `max_deliveries=1`→lands in `jarvis:dlq`, pending cleared.
- **Live acceptance**: run `jarvis ingest` + `jarvis consume`; create a throwaway
  `jarvis-m2-probe` (alpine sleep) and restart it (**not** jarvis-redis/postgres — that would
  cut the consumer's own connections); confirm `events tail` / `state show` / `trace`.

## Process note
Lightweight path (per saved preference): this spec is the record; subagent spec-review loop and
a separate writing-plans pass are skipped. Implementation proceeds directly.
