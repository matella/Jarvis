# Phase 5.5a — Durability (backups · DR · snapshots · retention) — detailed spec

> Date: 2026-05-30 · First milestone of the hardening foundation (Phase 5.5), itself the first
> milestone of the conversational-orchestrator program. The system is now central and persistent;
> losing Postgres = losing Jarvis. This makes the data durable and the recovery *tested*.

## Decisions
- **Backups:** scheduled `pg_dump` (compressed, timestamped logical dumps).
- **Target:** write to a dir on the remote box, then pull a copy off-box to the Mac (3-2-1-ish).
- **Compaction:** `snapshots` are **fast-restore checkpoints of the `state` projection**; events
  are **NEVER pruned** (Hard Rule 3 — the event log is the source of truth, replay-across-time
  stays intact). Bound growth only on *derived* stores (metrics; code_chunks already replace on
  reindex).

## Components
- **`ops/backup.py`** (new `ops/` module for operational chores):
  - `run_backup()` — `pg_dump` the configured DB → `<backup_dir>/jarvis-<utc-ts>.sql.gz` on the
    primary location; copy to the off-box location; enforce `backup_retention_count` (delete
    oldest beyond N) in both. Emits a `backup.completed` / `backup.failed` event (typed
    failure_class) so backups are observable + alertable.
  - `verify_restore(path=latest)` — restore the dump into a **scratch database**
    (`jarvis_restore_check`), run sanity checks (expected tables exist; row counts > 0; alembic
    version matches head), drop the scratch DB. The DR drill — a backup is only as good as a
    tested restore.
- **`state/snapshotter.py`** (snapshots = checkpoints):
  - `write_snapshot(conn)` — serialize the current `state` projection → `snapshots` row
    (`kind='state'`, `blob`=rows, `last_event_id`=max `events.id` at snapshot time).
  - `rebuild_state(conn)` — truncate `state`, load the latest snapshot blob, then replay events
    with `id > last_event_id` through `project()`. Used for DR / fast rebuild.
  - **Trigger (not a naive timer):** the consumer counts state-changing projections; snapshot when
    `change_count ≥ snapshot_change_threshold` OR `snapshot_heartbeat_min` elapsed since the last
    (meaningful-change + heartbeat backstop, per CLAUDE.md).
- **Retention:** reuse `metrics` `prune_older_than` (already built); document that events/incidents/
  intents/executions/contexts/playbooks are **kept** (source-of-truth / provenance).
- **Daemon:** add `backup` (periodic, `backup_interval_s`) and `snapshot` (heartbeat+change) as
  `jarvis run` workers.
- **CLI:** `jarvis backup [--once]`, `jarvis restore --verify [--file PATH]`,
  `jarvis snapshot [--once]`, `jarvis snapshot rebuild` (DR; destructive — confirms first).
- **config:** `backup_dir`, `backup_offbox_dir`, `backup_retention_count=14`,
  `backup_interval_s=86400`, `snapshot_heartbeat_min=60`, `snapshot_change_threshold=200`.
- **Migrations:** none — the `snapshots` table already exists (M1).

## Where the backup job runs
`pg_dump` runs against the configured DSN (works over the SSH tunnel when the daemon is on the
Mac, or locally once Jarvis is deployed on the box). Primary = `backup_dir`; off-box copy =
`backup_offbox_dir` (rsync/scp). Config-driven so it's correct in both deployment shapes.

## Testing → acceptance
- **Unit:** retention selection (keep newest N, delete the rest); snapshot blob (de)serialization;
  the snapshot trigger policy (fires on threshold OR heartbeat, not every event).
- **Integration (DB):** `run_backup` produces a dump file; `verify_restore` restores it into a
  scratch DB and the sanity checks pass; `write_snapshot` then `rebuild_state` reproduces the
  `state` projection exactly (snapshot + replay == live state).
- **Live acceptance:** `jarvis backup --once` writes a dump on the remote + a copy appears on the
  Mac; `jarvis restore --verify` restores the latest into a scratch DB and reports OK; corrupt/clear
  `state`, `jarvis snapshot rebuild`, and `state show` matches what it was — DR proven end to end.

## Process note
Lightweight path (saved preference): this is the build-time spec for 5.5a. Next detailed specs:
5.5b (self-observability + audit), then 5.5c (security primitives), then Phase 6a.
