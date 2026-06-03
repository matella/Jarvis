"""Calendar repository — local CRUD (truth) + mirror upsert + window accessors + search.

Local events are the source of truth and emit awareness events; mirror events (google/ics) are
upserted from a sync and are read-only (edits refused at the tool layer). `index=True` embeds local
events into the shared search hook; tests without an embedder pass `index=False`.
"""

from __future__ import annotations

from datetime import datetime

import psycopg

from jarvis.calendar.models import CalendarEvent, EventSource
from jarvis.events.models import utcnow
from jarvis.modules import search
from jarvis.modules.awareness import emit_awareness

_SOURCE = "calendar"
_COLS = (
    "id, source, external_uid, title, location, description, starts_at, ends_at, all_day, "
    "rrule, status, source_entity_ref, schema_version, created_at, updated_at, synced_at"
)


def _row_to_event(row: dict) -> CalendarEvent:
    return CalendarEvent(**row)


def _insert(conn: psycopg.Connection, e: CalendarEvent) -> None:
    conn.execute(
        f"INSERT INTO calendar_events ({_COLS}) VALUES "
        "(%(id)s, %(source)s, %(external_uid)s, %(title)s, %(location)s, %(description)s, "
        "%(starts_at)s, %(ends_at)s, %(all_day)s, %(rrule)s, %(status)s, %(source_entity_ref)s, "
        "%(schema_version)s, %(created_at)s, %(updated_at)s, %(synced_at)s)",
        {**e.model_dump(), "source": e.source.value, "status": e.status.value},
    )


def create_local(conn: psycopg.Connection, event: CalendarEvent, *,
                 correlation_id: str | None = None, index: bool = True) -> CalendarEvent:
    event = event.model_copy(update={"source": EventSource.local, "external_uid": None})
    _insert(conn, event)
    emit_awareness("calendar.event_created", source=_SOURCE, entity_ref=event.entity_ref,
                   correlation_id=correlation_id, title=event.title)
    if index:
        search.index_entity(source=_SOURCE, entity_ref=event.entity_ref, title=event.title,
                            text=event.search_text())
    return event


def get(conn: psycopg.Connection, event_id: str) -> CalendarEvent | None:
    row = conn.execute(
        f"SELECT {_COLS} FROM calendar_events WHERE id = %s", (event_id,)
    ).fetchone()
    return _row_to_event(row) if row else None


def update_local(conn: psycopg.Connection, event_id: str, *, title: str | None = None,
                 starts_at: datetime | None = None, ends_at: datetime | None = None,
                 location: str | None = None, description: str | None = None,
                 index: bool = True) -> CalendarEvent | None:
    current = get(conn, event_id)
    if current is None:
        return None
    if current.is_mirror:
        raise ValueError("mirror events are read-only; copy to a local event to edit")
    candidates = {"title": title, "starts_at": starts_at, "ends_at": ends_at,
                  "location": location, "description": description}
    merged = current.model_copy(update={k: v for k, v in candidates.items() if v is not None})
    merged = merged.model_copy(update={"updated_at": utcnow()})
    conn.execute(
        "UPDATE calendar_events SET title=%s, starts_at=%s, ends_at=%s, location=%s, "
        "description=%s, updated_at=%s WHERE id=%s",
        (merged.title, merged.starts_at, merged.ends_at, merged.location, merged.description,
         merged.updated_at, event_id),
    )
    emit_awareness("calendar.event_updated", source=_SOURCE, entity_ref=merged.entity_ref,
                   title=merged.title)
    if index:
        search.reindex_entity(source=_SOURCE, entity_ref=merged.entity_ref, title=merged.title,
                              text=merged.search_text())
    return merged


def delete_local(conn: psycopg.Connection, event_id: str, *, index: bool = True) -> bool:
    current = get(conn, event_id)
    if current is None:
        return False
    if current.is_mirror:
        raise ValueError("mirror events are read-only; they vanish on re-sync, not by delete")
    conn.execute("DELETE FROM calendar_events WHERE id = %s", (event_id,))
    emit_awareness("calendar.event_deleted", source=_SOURCE, entity_ref=current.entity_ref,
                   title=current.title)
    if index:
        search.purge_entity(current.entity_ref)
    return True


def upsert_mirror(conn: psycopg.Connection, event: CalendarEvent) -> CalendarEvent:
    """Upsert a mirrored (google/ics) event, deduped by (source, external_uid)."""
    if not event.is_mirror or not event.external_uid:
        raise ValueError("mirror upsert requires a non-local source and an external_uid")
    event = event.model_copy(update={"synced_at": utcnow()})
    conn.execute(
        f"INSERT INTO calendar_events ({_COLS}) VALUES "
        "(%(id)s, %(source)s, %(external_uid)s, %(title)s, %(location)s, %(description)s, "
        "%(starts_at)s, %(ends_at)s, %(all_day)s, %(rrule)s, %(status)s, %(source_entity_ref)s, "
        "%(schema_version)s, %(created_at)s, %(updated_at)s, %(synced_at)s) "
        "ON CONFLICT (source, external_uid) DO UPDATE SET title=EXCLUDED.title, "
        "location=EXCLUDED.location, description=EXCLUDED.description, "
        "starts_at=EXCLUDED.starts_at, ends_at=EXCLUDED.ends_at, all_day=EXCLUDED.all_day, "
        "status=EXCLUDED.status, synced_at=EXCLUDED.synced_at",
        {**event.model_dump(), "source": event.source.value, "status": event.status.value},
    )
    return event


def agenda(conn: psycopg.Connection, start: datetime, end: datetime) -> list[CalendarEvent]:
    """All events (local + mirror) overlapping [start, end), ordered by start."""
    rows = conn.execute(
        f"SELECT {_COLS} FROM calendar_events WHERE status != 'cancelled' AND starts_at < %s "
        "AND (ends_at IS NULL OR ends_at >= %s) ORDER BY starts_at ASC",
        (end, start),
    ).fetchall()
    return [_row_to_event(r) for r in rows]
