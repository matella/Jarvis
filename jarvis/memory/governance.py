"""Memory governance (cross-cutting track D) — list / forget / consolidate.

Memory shouldn't grow without bound or keep stale facts. `forget` removes a record (audited via a
`memory.forgotten` event); `consolidate` compacts a window of older episodic summaries into ONE
higher-level summary (one inference), stores it, and drops the originals — the same compaction idea
as snapshots, applied to semantic memory. All deterministic except the single summarize call.
"""

from __future__ import annotations

import psycopg

from jarvis import ids
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import emit_event
from jarvis.memory.store import MemoryRecord, PgVectorMemoryStore


def list_memories(
    conn: psycopg.Connection, *, kind: str | None = None, limit: int = 30
) -> list[dict]:
    sql = "SELECT id, kind, content, ts FROM memory"
    params: list[object] = []
    if kind:
        sql += " WHERE kind = %s"
        params.append(kind)
    sql += " ORDER BY ts DESC LIMIT %s"
    params.append(limit)
    return conn.execute(sql, params).fetchall()


def forget(conn: psycopg.Connection, mem_id: str) -> bool:
    """Delete a memory by id. Returns True if a row was removed; emits memory.forgotten."""
    cur = conn.execute("DELETE FROM memory WHERE id = %s", (mem_id,))
    removed = cur.rowcount > 0
    if removed:
        emit_event(Event(
            type="memory.forgotten", severity=Severity.info, source="memory",
            entity_ref=f"memory:{mem_id}", occurred_at=utcnow(),
            payload={"memory_id": mem_id}, correlation_id=ids.new_id(ids.CORRELATION),
        ))
    return removed


def _summarize_old(contents: list[str]) -> str:
    from jarvis.models import router

    joined = "\n\n".join(f"- {c}" for c in contents)
    prompt = (
        "Compress these older operational summaries into ONE concise higher-level summary "
        "(3-4 sentences), preserving recurring entities and unresolved issues:\n\n" + joined
    )
    resp = router.chat("reasoning", [{"role": "user", "content": prompt}])
    return str(resp["message"]["content"]).strip()


def consolidate(
    conn: psycopg.Connection, *, kind: str = "summary", keep_recent: int = 5,
    store: PgVectorMemoryStore | None = None,
) -> dict:
    """Compact older `kind` memories (all but the `keep_recent` newest) into one summary."""
    rows = conn.execute(
        "SELECT id, content FROM memory WHERE kind = %s ORDER BY ts DESC", (kind,)
    ).fetchall()
    old = rows[keep_recent:]
    if len(old) < 2:
        return {"consolidated": 0, "kept": len(rows), "summary": None}

    summary = _summarize_old([r["content"] for r in old])
    from jarvis.models.router import embed

    store = store or PgVectorMemoryStore()
    record = MemoryRecord(
        kind=kind, content=summary, embedding=embed(summary),
        metadata={"consolidated": True, "from_count": len(old)},
    )
    store.add(record)
    old_ids = [r["id"] for r in old]
    conn.execute("DELETE FROM memory WHERE id = ANY(%s)", (old_ids,))
    emit_event(Event(
        type="memory.consolidated", severity=Severity.info, source="memory",
        entity_ref=f"memory:{record.id}", occurred_at=utcnow(),
        payload={"kind": kind, "compacted": len(old), "into": record.id},
        correlation_id=ids.new_id(ids.CORRELATION),
    ))
    return {"consolidated": len(old), "kept": keep_recent, "summary": summary, "new_id": record.id}
