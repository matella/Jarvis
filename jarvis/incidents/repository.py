"""Incident persistence — thin SQL over psycopg3."""

from __future__ import annotations

import psycopg

from jarvis.incidents.models import Incident

_COLUMNS = (
    "incident_id, schema_version, window_label, severity, summary, root_cause, "
    "entity_refs, event_ids, event_count, context_ref, correlation_id, created_at"
)


def insert_incident(conn: psycopg.Connection, incident: Incident) -> None:
    conn.execute(
        f"INSERT INTO incidents ({_COLUMNS}) VALUES "
        "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            incident.incident_id,
            incident.schema_version,
            incident.window_label,
            incident.severity.value,
            incident.summary,
            incident.root_cause,
            incident.entity_refs,
            incident.event_ids,
            incident.event_count,
            incident.context_ref,
            incident.correlation_id,
            incident.created_at,
        ),
    )


def get_incident(conn: psycopg.Connection, incident_id: str) -> Incident | None:
    row = conn.execute(
        "SELECT * FROM incidents WHERE incident_id = %s", (incident_id,)
    ).fetchone()
    return Incident(**row) if row else None


def list_incidents(conn: psycopg.Connection, limit: int = 20) -> list[Incident]:
    rows = conn.execute(
        "SELECT * FROM incidents ORDER BY incident_id DESC LIMIT %s", (limit,)
    ).fetchall()
    return [Incident(**row) for row in rows]
