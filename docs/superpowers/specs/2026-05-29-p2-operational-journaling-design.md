# Phase 2 — Operational Journaling (design spec)

> Date: 2026-05-29 · Phase 2, final sub-project. A curated, human-readable operational
> timeline. (GPU scheduling, the other Phase 2 item, stays deferred per DECISIONS — one
> inference path; its telemetry seed already exists.)

## Decision: derived view, NOT a new table
The event log is already the append-only operational timeline (Hard Rule 3); incidents,
intents, and executions already exist as records. A persisted journal table would duplicate
the source of truth — the premature-architecture trap the project warns against. So journaling
is a **read-only aggregation** that merges existing records chronologically. No migration, no
new ingestion.

## Contents (curated)
The significant operational happenings, merged and time-sorted:
- **incidents** (correlated alerts) — by `created_at`.
- **intents** + **executions** — by `created_at`.
- **warning+ events** from operational sources only (`source` ∉ correlator/router/orchestrator/
  infrastructure_agent) — so `incident.correlated` / `execution.recorded` meta-events don't
  double-count the incident/execution rows.
Excludes info/debug lifecycle and model/inference telemetry.

## Components
- **`core/journal.py`**:
  - `JournalEntry` dataclass `{ts, kind (event|incident|intent|execution), severity, title, ref}`.
  - `build_journal(conn, since) -> list[JournalEntry]` — query each source, normalize to entries,
    merge, sort by `ts` ascending (reads like a diary).
- **CLI**: `jarvis journal --since 24h` → Rich timeline (time, kind, severity, what, ref).

## Testing → acceptance
- **Unit** (FakeConn routing by SQL substring): build_journal merges the four sources into one
  chronologically-sorted timeline; severities normalized (intent risk=high→warning, execution
  failure→warning); meta-source events excluded by the query.
- **Integration** (DB): seed a warning event (+ optionally an incident) → `build_journal`
  includes it in time order. Skips if DB down.
- **Live acceptance**: generate a couple of operational happenings (a container stop + a
  correlate run) → `jarvis journal --since 1h` shows a unified timeline (event → incident),
  oldest first.

## Phase 2 status after this
metrics ✓ · alert correlation ✓ · topology ✓ · operational journaling ✓ ·
GPU scheduling = deferred-by-design (DECISIONS), telemetry seed in place. Phase 2 complete.

## Process note
Lightweight path (saved preference): this spec is the record; subagent review loop + separate
writing-plans pass skipped. Implementation proceeds directly.
