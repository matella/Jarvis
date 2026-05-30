"""Audit log — record/query who did what. Recorded at the caller (the caller knows the actor)."""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.types.json import Json


def record(
    conn: psycopg.Connection, *, actor: str, action: str, target: str | None = None, **details: Any
) -> None:
    conn.execute(
        "INSERT INTO audit_log (actor, action, target, details) VALUES (%s, %s, %s, %s)",
        (actor, action, target, Json(details)),
    )


def list_audit(conn: psycopg.Connection, limit: int = 30) -> list[dict]:
    return conn.execute(
        "SELECT ts, actor, action, target, details FROM audit_log ORDER BY id DESC LIMIT %s",
        (limit,),
    ).fetchall()
