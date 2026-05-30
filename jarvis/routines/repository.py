"""Routine persistence."""

from __future__ import annotations

import psycopg
from psycopg.types.json import Json

from jarvis.routines.models import Routine


def insert_routine(conn: psycopg.Connection, routine: Routine) -> None:
    r = routine.as_row()
    conn.execute(
        "INSERT INTO routines (id, name, schedule, action, enabled, last_run, created_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (r["id"], r["name"], Json(r["schedule"]), Json(r["action"]),
         r["enabled"], r["last_run"], r["created_at"]),
    )


def list_routines(conn: psycopg.Connection, *, only_enabled: bool = False) -> list[Routine]:
    sql = "SELECT * FROM routines"
    if only_enabled:
        sql += " WHERE enabled = true"
    sql += " ORDER BY created_at"
    return [Routine(**row) for row in conn.execute(sql).fetchall()]


def get_routine(conn: psycopg.Connection, routine_id: str) -> Routine | None:
    row = conn.execute("SELECT * FROM routines WHERE id = %s", (routine_id,)).fetchone()
    return Routine(**row) if row else None


def mark_run(conn: psycopg.Connection, routine_id: str, when) -> None:
    conn.execute("UPDATE routines SET last_run = %s WHERE id = %s", (when, routine_id))
