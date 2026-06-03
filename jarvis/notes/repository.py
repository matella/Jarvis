"""Notes repository — single write path (CRUD + awareness + search + read accessors).

Search is the primary recall path for notes, so indexing matters here. `index=True` embeds title +
body into the shared module search hook; tests without an embedder pass `index=False`.
"""

from __future__ import annotations

import psycopg

from jarvis.events.models import utcnow
from jarvis.modules import search
from jarvis.modules.awareness import emit_awareness
from jarvis.notes.models import Note

_SOURCE = "notes"
_COLS = (
    "id, title, body_md, pinned, archived, tags, source_entity_ref, "
    "schema_version, created_at, updated_at"
)


def _row_to_note(row: dict) -> Note:
    return Note(**row)


def create(
    conn: psycopg.Connection, note: Note, *, correlation_id: str | None = None, index: bool = True
) -> Note:
    conn.execute(
        f"INSERT INTO notes ({_COLS}) VALUES "
        "(%(id)s, %(title)s, %(body_md)s, %(pinned)s, %(archived)s, %(tags)s, "
        "%(source_entity_ref)s, %(schema_version)s, %(created_at)s, %(updated_at)s)",
        note.model_dump(),
    )
    emit_awareness("note.created", source=_SOURCE, entity_ref=note.entity_ref,
                   correlation_id=correlation_id, title=note.title)
    if index:
        search.index_entity(
            source=_SOURCE, entity_ref=note.entity_ref, title=note.title, text=note.body_md
        )
    return note


def get(conn: psycopg.Connection, note_id: str) -> Note | None:
    row = conn.execute(f"SELECT {_COLS} FROM notes WHERE id = %s", (note_id,)).fetchone()
    return _row_to_note(row) if row else None


def update(
    conn: psycopg.Connection,
    note_id: str,
    *,
    title: str | None = None,
    body_md: str | None = None,
    pinned: bool | None = None,
    tags: list[str] | None = None,
    index: bool = True,
) -> Note | None:
    current = get(conn, note_id)
    if current is None:
        return None
    candidates = {"title": title, "body_md": body_md, "pinned": pinned, "tags": tags}
    updates = {k: v for k, v in candidates.items() if v is not None}
    merged = current.model_copy(update=updates).model_copy(update={"updated_at": utcnow()})
    # Re-validate (title derivation, tag normalization) by rebuilding the model.
    merged = Note(**merged.model_dump())
    conn.execute(
        "UPDATE notes SET title=%s, body_md=%s, pinned=%s, tags=%s, updated_at=%s WHERE id=%s",
        (merged.title, merged.body_md, merged.pinned, merged.tags, merged.updated_at, note_id),
    )
    emit_awareness("note.updated", source=_SOURCE, entity_ref=merged.entity_ref, title=merged.title)
    if index:
        search.reindex_entity(
            source=_SOURCE, entity_ref=merged.entity_ref, title=merged.title, text=merged.body_md
        )
    return merged


def delete(conn: psycopg.Connection, note_id: str, *, index: bool = True) -> bool:
    """Soft-delete (archived=true, kept) + purge from search."""
    current = get(conn, note_id)
    if current is None:
        return False
    conn.execute("UPDATE notes SET archived=true, updated_at=%s WHERE id=%s", (utcnow(), note_id))
    emit_awareness("note.archived", source=_SOURCE, entity_ref=current.entity_ref,
                   title=current.title)
    if index:
        search.purge_entity(current.entity_ref)
    return True


def recent(conn: psycopg.Connection, *, limit: int = 20) -> list[Note]:
    rows = conn.execute(
        f"SELECT {_COLS} FROM notes WHERE archived = false "
        "ORDER BY pinned DESC, updated_at DESC LIMIT %s",
        (limit,),
    ).fetchall()
    return [_row_to_note(r) for r in rows]
