"""Code-session persistence round-trip against a live DB."""

from __future__ import annotations

import psycopg
import pytest

from jarvis.code import repository
from jarvis.code.models import CodeSession, CodeStatus

pytestmark = pytest.mark.integration


def test_save_get_recent(db_conn: psycopg.Connection) -> None:
    db_conn.execute("DELETE FROM code_sessions")
    s = CodeSession(repo_path="/repos/x", task="fix bug", status=CodeStatus.ready,
                    diff_text="diff --git a/x b/x", files_changed=["x"])
    repository.save(db_conn, s)

    got = repository.get(db_conn, s.id)
    assert got is not None and got.status is CodeStatus.ready and got.files_changed == ["x"]

    # upsert → applied
    repository.save(db_conn, s.model_copy(update={
        "status": CodeStatus.applied, "applied": True, "applied_commit": "abc123",
    }))
    after = repository.get(db_conn, s.id)
    assert after.applied is True and after.applied_commit == "abc123"
    assert [r.id for r in repository.recent(db_conn)] == [s.id]
