"""Time-travel — reconstruct state as-of any past instant, and diff two instants.

Nearly free given the append-only event log: replay the container events up to a timestamp through
the SAME projection logic the live projector uses (status_for_type / signal_attr_for_type), in
memory, to get point-in-time state. `diff` answers "what changed since X?" — added/removed entities
and per-field changes — without any extra storage.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import psycopg

from jarvis.state.projector import signal_attr_for_type, status_for_type


def _apply(state: dict[str, dict[str, Any]], row: dict) -> None:
    """Fold one event into the in-memory state (mirrors projector.project, no DB)."""
    entity = row["entity_ref"]
    etype = row["type"]
    if not entity or not etype.startswith("container."):
        return
    status = status_for_type(etype)
    signal = signal_attr_for_type(etype)
    if status is None and signal is None:
        return
    cur = state.setdefault(entity, {"status": None, "attrs": {}})
    payload = row.get("payload") or {}
    cur["attrs"]["last_action"] = etype
    cur["attrs"]["last_severity"] = row.get("severity")
    if status is not None:
        cur["status"] = status
        for key in ("image", "exit_code", "health"):
            if payload.get(key) is not None:
                cur["attrs"][key] = payload[key]
    elif signal is not None:
        cur["attrs"][signal[0]] = signal[1]


def state_at(conn: psycopg.Connection, ts: datetime) -> dict[str, dict[str, Any]]:
    """Reconstruct the container-state projection as it stood at `ts`."""
    rows = conn.execute(
        "SELECT id, type, severity, entity_ref, payload, occurred_at FROM events "
        "WHERE type LIKE 'container.%%' AND occurred_at <= %s ORDER BY id",
        (ts,),
    ).fetchall()
    state: dict[str, dict[str, Any]] = {}
    for row in rows:
        _apply(state, row)
    return state


def diff(conn: psycopg.Connection, t1: datetime, t2: datetime) -> dict[str, Any]:
    """What changed between two instants: entities added / removed / with field changes."""
    a = state_at(conn, t1)
    b = state_at(conn, t2)
    added = sorted(set(b) - set(a))
    removed = sorted(set(a) - set(b))
    changed: dict[str, dict[str, Any]] = {}
    for entity in set(a) & set(b):
        if a[entity].get("status") != b[entity].get("status"):
            changed[entity] = {"status": [a[entity].get("status"), b[entity].get("status")]}
    return {"added": added, "removed": removed, "changed": changed}
