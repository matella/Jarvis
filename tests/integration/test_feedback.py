"""Cross-cutting B integration: feedback record → score → list round-trip on the live DB."""

from __future__ import annotations

import psycopg
import pytest

from jarvis import feedback

pytestmark = pytest.mark.integration


def test_feedback_roundtrip(db_conn: psycopg.Connection) -> None:
    tid = "int_feedback_itest"
    try:
        feedback.record(db_conn, target_type="intent", target_id=tid, rating=1, actor="itest")
        feedback.record(db_conn, target_type="intent", target_id=tid, rating=-1, actor="itest",
                        note="changed my mind")
        feedback.record(db_conn, target_type="intent", target_id=tid, rating=1, actor="itest")
        assert feedback.score(db_conn, target_type="intent", target_id=tid) == 1  # +1-1+1

        rows = feedback.list_feedback(db_conn, 10)
        mine = [r for r in rows if r["target_id"] == tid]
        assert len(mine) == 3
        assert any(r["note"] == "changed my mind" for r in mine)
    finally:
        db_conn.execute("DELETE FROM feedback WHERE target_id = %s", (tid,))
