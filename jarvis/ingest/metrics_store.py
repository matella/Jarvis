"""Persistence for raw metric samples (the telemetry store, separate from `state`)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import psycopg
from psycopg.types.json import Json

from jarvis.events.models import utcnow


def insert_samples(
    conn: psycopg.Connection, samples: list[tuple[str, str, dict[str, Any]]]
) -> int:
    """Bulk-insert (entity, kind, sample) rows. Returns the count written."""
    if not samples:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO metrics (entity, kind, sample) VALUES (%s, %s, %s)",
            [(entity, kind, Json(sample)) for entity, kind, sample in samples],
        )
    return len(samples)


def latest_per_entity(
    conn: psycopg.Connection, kind: str | None = None
) -> list[dict[str, Any]]:
    """Most recent sample for each entity (optionally filtered by kind)."""
    sql = (
        "SELECT DISTINCT ON (entity) entity, kind, sample, ts FROM metrics"
    )
    params: list[Any] = []
    if kind is not None:
        sql += " WHERE kind = %s"
        params.append(kind)
    sql += " ORDER BY entity, ts DESC"
    return conn.execute(sql, params).fetchall()


def prune_older_than(conn: psycopg.Connection, retention_hours: int) -> int:
    cutoff: datetime = utcnow() - timedelta(hours=retention_hours)
    cur = conn.execute("DELETE FROM metrics WHERE ts < %s", (cutoff,))
    return cur.rowcount
