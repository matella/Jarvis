"""Documents repository — CRUD + append-only version history + awareness + search + accessors.

Every save snapshots a `document_versions` row (cheap history); `restore` sets the body to a chosen
version (and snapshots that as a new version, so history is never rewritten). `index=True` embeds
title+body into the shared search hook; tests without an embedder pass `index=False`.
"""

from __future__ import annotations

import psycopg

from jarvis.documents.models import DocStatus, Document, DocumentVersion
from jarvis.events.models import utcnow
from jarvis.modules import search
from jarvis.modules.awareness import emit_awareness

_SOURCE = "documents"
_COLS = "id, title, body_md, status, source_entity_ref, schema_version, created_at, updated_at"


def _row_to_doc(row: dict) -> Document:
    return Document(**row)


def _snapshot(conn: psycopg.Connection, doc_id: str, body_md: str, *, author: str,
              summary: str | None) -> DocumentVersion:
    version = DocumentVersion(document_id=doc_id, body_md=body_md, author=author, summary=summary)
    conn.execute(
        "INSERT INTO document_versions (id, document_id, body_md, author, summary, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (version.id, doc_id, body_md, author, summary, version.created_at),
    )
    return version


def create(
    conn: psycopg.Connection, doc: Document, *, author: str = "operator",
    correlation_id: str | None = None, index: bool = True,
) -> Document:
    conn.execute(
        f"INSERT INTO documents ({_COLS}) VALUES "
        "(%(id)s, %(title)s, %(body_md)s, %(status)s, %(source_entity_ref)s, "
        "%(schema_version)s, %(created_at)s, %(updated_at)s)",
        doc.model_dump(),
    )
    _snapshot(conn, doc.id, doc.body_md, author=author, summary="created")
    emit_awareness("document.created", source=_SOURCE, entity_ref=doc.entity_ref,
                   correlation_id=correlation_id, title=doc.title)
    if index:
        search.index_entity(source=_SOURCE, entity_ref=doc.entity_ref, title=doc.title,
                            text=doc.body_md)
    return doc


def get(conn: psycopg.Connection, doc_id: str) -> Document | None:
    row = conn.execute(f"SELECT {_COLS} FROM documents WHERE id = %s", (doc_id,)).fetchone()
    return _row_to_doc(row) if row else None


def update(
    conn: psycopg.Connection, doc_id: str, *, title: str | None = None, body_md: str | None = None,
    status: DocStatus | None = None, author: str = "operator", summary: str | None = None,
    index: bool = True,
) -> Document | None:
    current = get(conn, doc_id)
    if current is None:
        return None
    candidates = {"title": title, "body_md": body_md, "status": status}
    merged = current.model_copy(update={k: v for k, v in candidates.items() if v is not None})
    merged = Document(**merged.model_dump()).model_copy(update={"updated_at": utcnow()})
    conn.execute(
        "UPDATE documents SET title=%s, body_md=%s, status=%s, updated_at=%s WHERE id=%s",
        (merged.title, merged.body_md, merged.status.value, merged.updated_at, doc_id),
    )
    if body_md is not None:
        _snapshot(conn, doc_id, merged.body_md, author=author, summary=summary or "edit")
    emit_awareness("document.updated", source=_SOURCE, entity_ref=merged.entity_ref,
                   title=merged.title)
    if index:
        search.reindex_entity(source=_SOURCE, entity_ref=merged.entity_ref, title=merged.title,
                              text=merged.body_md)
    return merged


def versions(conn: psycopg.Connection, doc_id: str) -> list[DocumentVersion]:
    rows = conn.execute(
        "SELECT id, document_id, body_md, author, summary, created_at "
        "FROM document_versions WHERE document_id = %s ORDER BY created_at DESC",
        (doc_id,),
    ).fetchall()
    return [DocumentVersion(**r) for r in rows]


def restore(conn: psycopg.Connection, doc_id: str, version_id: str, *, index: bool = True
            ) -> Document | None:
    row = conn.execute(
        "SELECT body_md FROM document_versions WHERE id = %s AND document_id = %s",
        (version_id, doc_id),
    ).fetchone()
    if row is None:
        return None
    return update(conn, doc_id, body_md=row["body_md"], author="operator",
                  summary=f"restored from {version_id}", index=index)


def delete(conn: psycopg.Connection, doc_id: str, *, index: bool = True) -> bool:
    current = get(conn, doc_id)
    if current is None:
        return False
    conn.execute("UPDATE documents SET status='archived', updated_at=%s WHERE id=%s",
                 (utcnow(), doc_id))
    emit_awareness("document.archived", source=_SOURCE, entity_ref=current.entity_ref,
                   title=current.title)
    if index:
        search.purge_entity(current.entity_ref)
    return True


def recent(conn: psycopg.Connection, *, limit: int = 20) -> list[Document]:
    rows = conn.execute(
        f"SELECT {_COLS} FROM documents WHERE status != 'archived' "
        "ORDER BY updated_at DESC LIMIT %s",
        (limit,),
    ).fetchall()
    return [_row_to_doc(r) for r in rows]
