"""Documents repository round-trip + version history/restore against a live DB (index=False)."""

from __future__ import annotations

import psycopg
import pytest

from jarvis.documents import repository
from jarvis.documents.models import Document

pytestmark = pytest.mark.integration


def test_crud_and_version_history(db_conn: psycopg.Connection) -> None:
    db_conn.execute("DELETE FROM documents")
    doc = Document(title="Essay", body_md="v1 body")
    repository.create(db_conn, doc, index=False)

    repository.update(db_conn, doc.id, body_md="v2 body", summary="second draft", index=False)
    repository.update(db_conn, doc.id, body_md="v3 body", summary="third draft", index=False)

    vers = repository.versions(db_conn, doc.id)
    assert [v.body_md for v in vers][:3] == ["v3 body", "v2 body", "v1 body"]  # newest first

    # restore an earlier version → current body changes, history grows (never rewritten)
    v1 = vers[-1]
    repository.restore(db_conn, doc.id, v1.id, index=False)
    assert repository.get(db_conn, doc.id).body_md == "v1 body"
    assert len(repository.versions(db_conn, doc.id)) == 4

    assert repository.delete(db_conn, doc.id, index=False) is True
    assert repository.get(db_conn, doc.id).status.value == "archived"
    assert repository.recent(db_conn) == []
