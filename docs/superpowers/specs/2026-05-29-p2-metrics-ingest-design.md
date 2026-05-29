# Phase 2 — Metrics Ingest (design spec)

> Date: 2026-05-29 · Phase 2, first sub-project (see `docs/PLAN.md` / `docs/ARCHITECTURE.md`).
> Resource telemetry (CPU/mem/GPU) that is NOT in the Docker events stream.

## The constraint that shapes everything
Metrics are a firehose. Two Hard Rules bind the design:
- **Resist low-signal events** → raw samples must NOT become events.
- **Only the projector writes `state`** (a projection of the event log) → a poller must NOT
  write `state` either.

So: a deterministic poller writes raw samples to a **separate `metrics` telemetry table**, and
emits **signal events only** (threshold crossings, debounced) to the existing spine. `state`
stays event-sourced and pure; the event log stays meaningful; raw values stay queryable.

## Decisions
- **Sources**: `docker stats --no-stream --format {{json .}}` over the SSH context (per-container
  CPU/mem/IO) + `ssh <REMOTE_SSH> nvidia-smi --query-gpu=…` (GPU util/mem/temp). Both confirmed.
- **`metrics` table is generic**: `(id bigserial, entity, kind∈{container,gpu}, sample jsonb, ts)`.
  Not a boundary/event-sourced record → no schema_version/causal ids (like state/snapshots);
  bigserial because it's high-volume time-series, not a prefixed-ULID boundary object.

## Schema — migration 0003
`metrics(id bigserial PK, entity text, kind text CHECK in (container,gpu), sample jsonb, ts
timestamptz default now())`; indexes `(entity, ts DESC)` and `(ts)` (retention prune).

## Components (MAP.md seams)
- **`ingest/metrics.py`**:
  - `sample_docker_stats(context) -> list[Sample]` — parse CPUPerc/MemUsage/MemPerc/Net/Block;
    unit parsers (`_parse_pct`, `_parse_bytes` for MiB/GiB/kB/MB/B).
  - `sample_gpu(remote_ssh) -> list[Sample]` — nvidia-smi CSV → util/mem_used/mem_total/temp.
  - `run_poller(*, once)` — each cycle: sample → bulk insert to `metrics` → threshold eval with
    **in-memory debounce** (emit `*_high` only on False→True, `*_normal` on recovery) → prune rows
    older than `metrics_retention_hours`.
- **Signal event types** (the only metrics that reach the log): `container.cpu_high`/`_normal`,
  `container.memory_high`/`_normal`, `gpu.memory_high`/`_normal`, `gpu.utilization_high`/`_normal`.
  `entity_ref=container:<name>` / `gpu:<idx>`; payload = triggering value + threshold; each roots a
  new correlation_id. Flow through consumer→log→`trace`; visible to the infra agent.
- **config**: `metrics_poll_interval_s=30`, `metrics_retention_hours=24`, `cpu_high_pct=85`,
  `mem_high_pct=90`, `gpu_util_high_pct=90`, `gpu_mem_high_pct=90`, `remote_ssh` (from `.env`).
- **`metrics/repository.py`** (under state? no — put in ingest or a small `metrics` store): insert
  samples, latest-per-entity, prune. Kept in `ingest/metrics_store.py`.
- **CLI**: `jarvis metrics` (run poller; `--once`), `jarvis metrics show [--kind] [-n]`.

## Testing → acceptance
- **Unit** (no DB/docker): `_parse_pct`, `_parse_bytes`; docker-stats-json → sample;
  nvidia-smi-csv → sample; threshold+debounce (transition emits once, steady-state silent,
  recovery emits `_normal`).
- **Integration** (DB via tunnel + docker context): `run_poller(once=True)` writes metrics rows
  for real containers + GPU; latest-per-entity query; prune removes old rows. Skips if unavailable.
- **Live acceptance**: `jarvis metrics --once` samples + writes; `jarvis metrics show` displays
  current usage; a CPU-burner container crosses threshold → `container.cpu_high` in `events tail`,
  `container.cpu_normal` when stopped — no per-sample flooding of the log.

## Deferred (clean follow-ups)
- Reflect signal events into `state.attrs` via the projector (cpu_status etc.).
- cAdvisor/Prometheus source; per-process metrics; alert correlation across signals.

## Process note
Lightweight path (saved preference): this spec is the record; subagent review loop + separate
writing-plans pass skipped. Implementation proceeds directly.
