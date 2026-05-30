"""State snapshots — fast-restore checkpoints of the `state` projection.

Snapshots are compaction checkpoints, NOT event pruning: the event log stays the source of truth
(Hard Rule 3). A snapshot stores the current `state` rows + the `last_event_id` it reflects;
rebuild = load the snapshot, then replay only events after it. Trigger = heartbeat, but only when
new events have arrived (meaningful-change + heartbeat backstop, never a naive timer).
"""

from __future__ import annotations

import time
from datetime import datetime

import psycopg
from psycopg.types.json import Json

from jarvis import db, ids
from jarvis.config import get_settings
from jarvis.events.models import Event
from jarvis.state.projector import project


def _max_event_id(conn: psycopg.Connection) -> str | None:
    return conn.execute("SELECT max(id) AS m FROM events").fetchone()["m"]


def _last_snapshot_event(conn: psycopg.Connection) -> str | None:
    row = conn.execute(
        "SELECT last_event_id FROM snapshots WHERE kind = 'state' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return row["last_event_id"] if row else None


def write_snapshot(conn: psycopg.Connection) -> str:
    rows = conn.execute(
        "SELECT entity, kind, status, attrs, updated_at, last_event_id FROM state"
    ).fetchall()
    state = [
        {
            "entity": r["entity"], "kind": r["kind"], "status": r["status"],
            "attrs": r["attrs"], "updated_at": r["updated_at"].isoformat(),
            "last_event_id": r["last_event_id"],
        }
        for r in rows
    ]
    snap_id = ids.new_id(ids.SNAPSHOT)
    conn.execute(
        "INSERT INTO snapshots (id, kind, blob, last_event_id) VALUES (%s, 'state', %s, %s)",
        (snap_id, Json({"state": state}), _max_event_id(conn)),
    )
    return snap_id


def rebuild_state(conn: psycopg.Connection) -> dict:
    """DR / fast rebuild: load the latest snapshot, then replay events after it."""
    snap = conn.execute(
        "SELECT blob, last_event_id FROM snapshots WHERE kind = 'state' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if snap is None:
        raise RuntimeError("no state snapshot to rebuild from")

    with conn.transaction():
        conn.execute("TRUNCATE state")
        for r in snap["blob"]["state"]:
            conn.execute(
                "INSERT INTO state (entity, kind, status, attrs, updated_at, last_event_id) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (r["entity"], r["kind"], r["status"], Json(r["attrs"]),
                 datetime.fromisoformat(r["updated_at"]), r["last_event_id"]),
            )
        after = snap["last_event_id"] or ""
        events = conn.execute(
            "SELECT * FROM events WHERE id > %s ORDER BY id", (after,)
        ).fetchall()
        for row in events:
            project(conn, Event(**row))
    return {"restored_rows": len(snap["blob"]["state"]), "replayed_events": len(events)}


def run_snapshotter(*, once: bool = False) -> None:
    interval = get_settings().snapshot_heartbeat_min * 60
    while True:
        with db.connect(autocommit=True) as conn:
            current = _max_event_id(conn)
            if current is not None and current != _last_snapshot_event(conn):
                snap_id = write_snapshot(conn)
                print(f"[snapshot] wrote {snap_id} (last_event={current})", flush=True)
        if once:
            return
        time.sleep(interval)
