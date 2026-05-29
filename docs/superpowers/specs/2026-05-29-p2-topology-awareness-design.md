# Phase 2 — Topology Awareness (design spec)

> Date: 2026-05-29 · Phase 2, third sub-project. A deterministic service-dependency graph
> derived from container labels/network config — and wired into alert correlation so
> root-cause is grounded in real dependencies, not guessed.

## Deterministic boundary
Topology is derived entirely by deterministic code from `docker inspect` (labels + network
config). No LLM. It's a derived store like `metrics` (builder-written, not event-sourced, not
the `state` projection).

## Decisions
- **Relations**: `depends_on` (compose label), `network_mode` (container:<id> routing), and
  `same_project` (compose stack grouping). Shared-network edges excluded (noisy).
- **Wire into correlation now**: the correlator includes a "Known dependencies" section for a
  cluster's entities in its prompt.

## Schema — migration 0005
`topology(src_entity text, dst_entity text, relation text CHECK in
(depends_on, network_mode, same_project), attrs jsonb default '{}', updated_at timestamptz
default now(), PRIMARY KEY (src_entity, dst_entity, relation))`; indexes on src_entity, dst_entity.
Entities use the `container:<name>` convention.

## Components
- **`ingest/topology.py`**:
  - `_inspect_all(context) -> list[dict]` — `docker inspect --format {{json .}}` over running
    containers; extract Name, Id, labels(project/service/depends_on), HostConfig.NetworkMode.
  - `_build_edges(inspections) -> list[Edge]` (pure, unit-tested):
    - **same_project**: pairs sharing `com.docker.compose.project`.
    - **depends_on**: parse `com.docker.compose.depends_on` (`svc:cond:restart`, comma-sep) →
      resolve service name → container via a `(project, service) → name` map.
    - **network_mode**: `NetworkMode == "container:<id>"` → resolve `<id>` → name.
    - all edges are `container:<src> --rel--> container:<dst>`.
  - `build_topology()` — inspect → derive → write the full current edge set atomically
    (DELETE all + INSERT within one tx; small current snapshot).
  - `edges_for(conn, entities) -> list[tuple]` — edges where src or dst ∈ entities.
- **correlation wiring** (`agents/correlator.py`): fetch `edges_for(cluster entities)` and
  render a "Known dependencies:" block into the cluster prompt (same one-shot call).
- **CLI**: `jarvis topology build`, `jarvis topology show`.

## Testing → acceptance
- **Unit** (no docker): `_build_edges` over synthetic inspect dicts — same_project grouping,
  depends_on resolution via the (project,service) map, network_mode id→name resolution; the
  correlator's dependency-section rendering.
- **Integration** (docker via context + DB): `build_topology()` writes edges incl. the real
  `qbittorrent → gluetun` (network_mode + depends_on); `edges_for` query. Skips if unavailable.
- **Live acceptance**: `topology build` + `show` (real edges, read-only inspect — safe); then a
  self-contained grounded-correlation demo with two throwaway containers (one
  `--network container:<base>`): build → edge appears; stop both → burst → `correlate` → the
  incident prompt carries the dependency. Cleaned up after.

## Deferred
shared_network edges; cross-host topology; topology change events; persisting the topology slice
into each incident record.

## Process note
Lightweight path (saved preference): this spec is the record; subagent review loop + separate
writing-plans pass skipped. Implementation proceeds directly.
