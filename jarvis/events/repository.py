"""Event persistence — thin SQL over psycopg3. The caller owns the transaction."""

from __future__ import annotations

import psycopg
from psycopg.types.json import Json

from jarvis.events.models import Event

_COLUMNS = (
    "id, schema_version, type, severity, source, entity_ref, "
    "occurred_at, recorded_at, payload, correlation_id, causation_id"
)


def insert_event(conn: psycopg.Connection, event: Event) -> None:
    # ON CONFLICT DO NOTHING: the stream is at-least-once, so a redelivered event
    # must be a harmless no-op (events are an append-only, immutable source of truth).
    conn.execute(
        f"INSERT INTO events ({_COLUMNS}) VALUES "
        "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
        (
            event.id,
            event.schema_version,
            event.type,
            event.severity.value,
            event.source,
            event.entity_ref,
            event.occurred_at,
            event.recorded_at,
            Json(event.payload),
            event.correlation_id,
            event.causation_id,
        ),
    )


def get_event(conn: psycopg.Connection, event_id: str) -> Event | None:
    row = conn.execute("SELECT * FROM events WHERE id = %s", (event_id,)).fetchone()
    return Event(**row) if row else None
