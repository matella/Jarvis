"""Tasks repository round-trip against a live DB (no search indexing — index=False, no embedder)."""

from __future__ import annotations

from datetime import timedelta

import psycopg
import pytest

from jarvis.events.models import utcnow
from jarvis.tasks import repository
from jarvis.tasks.models import Task, TaskPriority, TaskStatus

pytestmark = pytest.mark.integration


def test_crud_lifecycle(db_conn: psycopg.Connection) -> None:
    db_conn.execute("DELETE FROM tasks")
    soon = utcnow() + timedelta(hours=2)
    task = Task(title="Pay rent", notes="bank transfer", priority=TaskPriority.high, due_at=soon)
    repository.create(db_conn, task, index=False)

    got = repository.get(db_conn, task.id)
    assert got is not None and got.title == "Pay rent" and got.priority is TaskPriority.high

    repository.update(db_conn, task.id, status=TaskStatus.doing, notes="started", index=False)
    assert repository.get(db_conn, task.id).status is TaskStatus.doing

    assert [t.id for t in repository.list_open(db_conn)] == [task.id]
    assert [t.id for t in repository.due_before(db_conn, soon + timedelta(hours=1))] == [task.id]

    repository.complete(db_conn, task.id)
    done = repository.get(db_conn, task.id)
    assert done.status is TaskStatus.done and done.completed_at is not None
    assert repository.list_open(db_conn) == []  # completed → not open

    assert repository.delete(db_conn, task.id, index=False) is True
    assert repository.get(db_conn, task.id).status is TaskStatus.dropped  # soft-delete kept


def test_subtask_parent_link(db_conn: psycopg.Connection) -> None:
    db_conn.execute("DELETE FROM tasks")
    parent = Task(title="Move flat")
    repository.create(db_conn, parent, index=False)
    child = Task(title="Pack kitchen", parent_id=parent.id)
    repository.create(db_conn, child, index=False)
    assert repository.get(db_conn, child.id).parent_id == parent.id
