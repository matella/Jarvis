# Consolidation — `jarvis run` daemon + metric→state reflection (design spec)

> Date: 2026-05-29 · Off-plan consolidation (user-approved). Make the spine run continuously
> instead of in bursts, and make `state` reflect resource health.

## Problem
Today the collectors run as separate manual foreground processes (`jarvis ingest`,
`consume`, `metrics run`), and nothing drains the stream between demos → consume-backlog.
Jarvis is *invoked*, not *running*.

## Part A — supervised daemon
- **`core/supervisor.py`**:
  - `_supervise(name, fn, stop)` — run `fn()` in a loop; on exception log + backoff + retry
    (unless `stop` set). Collector loops (ingest/consume/metrics) are infinite; this restarts
    them if they crash.
  - `_periodic(fn, interval_s, stop)` — call `fn()` every interval (topology, deploy detect).
  - `workers(stop)` — returns `[(name, callable)]`: ingest (`run_ingester`), consume
    (`run_forever`), metrics (`run_poller`), topology (`_periodic(build_topology, 300)`),
    deploy (`_periodic(detect_deployments, 120)`). Exposed for testing (names assertable).
  - `run()` — start a daemon thread per worker, wait until KeyboardInterrupt → set stop, exit.
  - One inference semaphore already serializes model calls across threads; each collector opens
    its own short-lived DB connection (psycopg connections are not shared across threads).
- **config**: `topology_interval_s=300`, `deploy_interval_s=120`.
- **CLI**: `jarvis run` (starts everything; Ctrl-C stops). Prints with flush so piped logs work.

## Part B — metric signals → state.attrs
Extend `state/projector.py`: in addition to container lifecycle, project the metric signal
events into `state.attrs` (status unchanged; monotonic `last_event_id` guard still applies):
- `container.cpu_high` → `attrs.cpu_status = high`; `container.cpu_normal` → `normal`.
- `container.memory_high` → `attrs.mem_status = high`; `container.memory_normal` → `normal`.
So `jarvis state show` shows operational health, not just lifecycle.

## Testing → acceptance
- **Unit**: `workers(stop)` returns the expected worker names without running them; projector
  maps signal types → (attrs key, value) via a pure helper.
- **Integration**: publish a `container.cpu_high` event → consume → `state.attrs.cpu_status=high`
  for that entity (lifecycle status untouched).
- **Live smoke**: `jarvis run` for ~15s → it ingests + consumes continuously (no backlog grows);
  Ctrl-C/stop cleanly; a cpu signal reflects into `state show`.

## Process note
Lightweight path (saved preference): this spec is the record; subagent review loop + separate
writing-plans pass skipped. Implementation proceeds directly.
