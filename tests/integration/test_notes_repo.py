"""Notes repository round-trip against a live DB (index=False — no embedder)."""

from __future__ import annotations

import psycopg
import pytest

from jarvis.notes import repository
from jarvis.notes.models import Note

pytestmark = pytest.mark.integration


def test_crud_lifecycle(db_conn: psycopg.Connection) -> None:
    db_conn.execute("DELETE FROM notes")
    note = Note(body_md="# Ideas\nbuild a thing", tags=["misc"])
    repository.create(db_conn, note, index=False)

    got = repository.get(db_conn, note.id)
    assert got is not None and got.title == "Ideas" and got.tags == ["misc"]

    repository.update(
        db_conn, note.id, body_md="# Ideas\nbuild two things", pinned=True, index=False
    )
    after = repository.get(db_conn, note.id)
    assert after.pinned is True and "two things" in after.body_md

    assert [n.id for n in repository.recent(db_conn)] == [note.id]

    assert repository.delete(db_conn, note.id, index=False) is True
    assert repository.get(db_conn, note.id).archived is True  # soft-delete kept
    assert repository.recent(db_conn) == []  # archived → not in recent
