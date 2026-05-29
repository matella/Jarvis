# Phase 2 — Alert Correlation (design spec)

> Date: 2026-05-29 · Phase 2, second sub-project (after metrics ingest). Group related
> alerts, suppress duplicates, infer a likely root cause — PLAN's "N alerts → one incident".

## Deterministic boundary
Deterministic code decides WHAT correlates (temporal-burst clustering + dedup); the LLM only
explains a cluster it is handed (root-cause hypothesis + summary). The model never picks what
is related and never invents events.

## Decisions
- **Dedicated `incidents` table** (migration 0004), carrying `context_ref` for explain/replay.
- **Deterministic clustering + one-shot LLM root-cause** per cluster.
- **warning+ severity only** feeds correlation (the actual alerts; info/debug excluded).

## Schema — migration 0004
`incidents(incident_id PK inc_<ulid>, schema_version, window text, severity text CHECK in the
5 levels, summary text, root_cause text, entity_refs text[], event_ids text[], event_count int,
context_ref text, correlation_id text, created_at timestamptz)`; index on `created_at`.
First-class operational record (has schema_version + correlation_id); links many source events
via `event_ids[]` (multi-parent, so no single causation_id).

## Components
- **`incidents/models.py`** — `Incident`; `IncidentAnalysis {summary, root_cause}` (model JSON out).
- **`incidents/repository.py`** — `insert_incident` / `list_incidents` / `get_incident`.
- **`agents/correlator.py`** — `correlate(since) -> list[Incident]`:
  1. fetch warning/error/critical events in window (deterministic).
  2. **temporal-burst clustering**: sort by occurred_at; extend the current cluster while the gap
     to the previous alert ≤ `incident_cluster_gap_s` (300); else start a new cluster.
  3. **dedup** within a cluster: collapse repeats keyed (type, entity_ref) → one line with a count.
  4. clusters with ≥ `incident_min_alerts` (2) → candidate incidents.
  5. per cluster: render alert lines → `save_context` (context_ref) → `router.chat(reasoning,
     format=json)` → validated `IncidentAnalysis` → `Incident` (severity=max in cluster,
     entity_refs/event_ids from cluster, new correlation_id) → `insert_incident` →
     emit `incident.correlated` (entity_ref=incident:<id>).
- **config**: `incident_cluster_gap_s=300`, `incident_min_alerts=2`.
- **CLI**: `jarvis correlate --since 1h`; `jarvis incidents list`; `jarvis incidents show <id>`.

## Event type added
`incident.correlated` (severity = the incident's; payload: summary, event_count, root_cause).

## Testing → acceptance
- **Unit** (no model/DB): clustering (two bursts separated by a long gap → two clusters; one
  burst → one cluster); dedup with counts; min_alerts threshold drops singletons;
  `IncidentAnalysis` parse/validate (good JSON, bad JSON rejected).
- **Integration** (DB + Ollama): seed a burst of warning+ events → `correlate` produces one
  incident whose `event_ids` link the alerts, persisted + `context_ref` stored. Skips if model down.
- **Live acceptance**: stop several throwaway containers in a short window → ingest+consume →
  `jarvis correlate --since 1h` → one incident grouping the deaths w/ a root-cause summary +
  linked event_ids; `jarvis incidents show` displays it.

## Deferred
Topology/dependency-aware root cause (no topology graph yet); auto/continuous correlation
(ambient, Phase 5); feeding incidents to the infra agent as intent triggers.

## Process note
Lightweight path (saved preference): this spec is the record; subagent review loop + separate
writing-plans pass skipped. Implementation proceeds directly.
