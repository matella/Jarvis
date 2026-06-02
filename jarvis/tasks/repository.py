"""Tasks repository — the single write path (CRUD + awareness + search indexing + read accessors).

The operator (UI/REST) and Jarvis (Intent → tool) both write through here. Each significant change
emits a light awareness event (best-effort) and keeps the search index in sync. `index=True` embeds
into the shared module search hook; tests without an embedder pass `index=False`.
"""

from __future__ import annotations

from datetime import datetime

import psycopg

from jarvis.events.models import utcnow
from jarvis.modules import search
from jarvis.modules.awareness import emit_awareness
from jarvis.tasks.models import Task, TaskPriority, TaskStatus

_SOURCE = "tasks"
_COLS = (
    "id, title, notes, status, priority, due_at, completed_at, parent_id, "
    "source_entity_ref, schema_version, created_at, updated_at"
)


def _row_to_task(row: dict) -> Task:
    return Task(**row)


def create(
    conn: psycopg.Connection, task: Task, *, correlation_id: str | None = None, index: bool = True
) -> Task:
    conn.execute(
        f"INSERT INTO tasks ({_COLS}) VALUES "
        "(%(id)s, %(title)s, %(notes)s, %(status)s, %(priority)s, %(due_at)s, %(completed_at)s, "
        "%(parent_id)s, %(source_entity_ref)s, %(schema_version)s, %(created_at)s, %(updated_at)s)",
        task.model_dump(),
    )
    emit_awareness(
        "task.created", source=_SOURCE, entity_ref=task.entity_ref,
        correlation_id=correlation_id, title=task.title, priority=task.priority.value,
    )
    if index:
        search.index_entity(
            source=_SOURCE, entity_ref=task.entity_ref, title=task.title, text=task.notes
        )
    return task


def get(conn: psycopg.Connection, task_id: str) -> Task | None:
    row = conn.execute(f"SELECT {_COLS} FROM tasks WHERE id = %s", (task_id,)).fetchone()
    return _row_to_task(row) if row else None


def update(
    conn: psycopg.Connection,
    task_id: str,
    *,
    title: str | None = None,
    notes: str | None = None,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    due_at: datetime | None = None,
    set_due: bool = False,  # explicit so due_at=None can clear it
    index: bool = True,
) -> Task | None:
    current = get(conn, task_id)
    if current is None:
        return None
    merged = current.model_copy(
        update={
            k: v
            for k, v in {
                "title": title, "notes": notes, "status": status, "priority": priority,
            }.items()
            if v is not None
        }
    )
    if set_due:
        merged = merged.model_copy(update={"due_at": due_at})
    merged = merged.model_copy(update={"updated_at": utcnow()})
    conn.execute(
        "UPDATE tasks SET title=%s, notes=%s, status=%s, priority=%s, due_at=%s, updated_at=%s "
        "WHERE id=%s",
        (merged.title, merged.notes, merged.status.value, merged.priority.value,
         merged.due_at, merged.updated_at, task_id),
    )
    emit_awareness("task.updated", source=_SOURCE, entity_ref=merged.entity_ref, title=merged.title)
    if index:
        search.reindex_entity(
            source=_SOURCE, entity_ref=merged.entity_ref, title=merged.title, text=merged.notes
        )
    return merged


def complete(conn: psycopg.Connection, task_id: str) -> Task | None:
    current = get(conn, task_id)
    if current is None:
        return None
    now = utcnow()
    conn.execute(
        "UPDATE tasks SET status='done', completed_at=%s, updated_at=%s WHERE id=%s",
        (now, now, task_id),
    )
    emit_awareness("task.completed", source=_SOURCE, entity_ref=current.entity_ref,
                   title=current.title)
    return current.model_copy(update={"status": TaskStatus.done, "completed_at": now})


def delete(conn: psycopg.Connection, task_id: str, *, index: bool = True) -> bool:
    """Soft-delete (status='dropped', kept for audit) + purge from search."""
    current = get(conn, task_id)
    if current is None:
        return False
    conn.execute(
        "UPDATE tasks SET status='dropped', updated_at=%s WHERE id=%s", (utcnow(), task_id)
    )
    emit_awareness("task.dropped", source=_SOURCE, entity_ref=current.entity_ref,
                   title=current.title)
    if index:
        search.purge_entity(current.entity_ref)
    return True


# --- read accessors (conversation context + daily brief) -----------------------------------------

def list_open(conn: psycopg.Connection, *, limit: int = 50) -> list[Task]:
    rows = conn.execute(
        f"SELECT {_COLS} FROM tasks WHERE status IN ('open','doing') "
        "ORDER BY (due_at IS NULL), due_at ASC, created_at ASC LIMIT %s",
        (limit,),
    ).fetchall()
    return [_row_to_task(r) for r in rows]


def due_before(conn: psycopg.Connection, when: datetime, *, limit: int = 50) -> list[Task]:
    rows = conn.execute(
        f"SELECT {_COLS} FROM tasks WHERE status IN ('open','doing') AND due_at IS NOT NULL "
        "AND due_at <= %s ORDER BY due_at ASC LIMIT %s",
        (when, limit),
    ).fetchall()
    return [_row_to_task(r) for r in rows]
