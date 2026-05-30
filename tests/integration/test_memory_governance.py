"""Cross-cutting D integration: memory forget + consolidate against the live DB (model mocked).

forget removes a record; consolidate compacts older summaries into one (the summarize call + embed
are mocked so it runs offline). Both leave the store in the expected state and clean up after.
"""

from __future__ import annotations

import psycopg
import pytest

from jarvis.memory import governance
from jarvis.memory.store import MemoryRecord, PgVectorMemoryStore

pytestmark = pytest.mark.integration


def _seed(store: PgVectorMemoryStore, kind: str, n: int) -> list[str]:
    ids_: list[str] = []
    for i in range(n):
        rec = MemoryRecord(kind=kind, content=f"gov-itest summary {i}", embedding=[0.0] * 768)
        store.add(rec)
        ids_.append(rec.id)
    return ids_


def test_forget_removes_record(db_conn: psycopg.Connection) -> None:
    store = PgVectorMemoryStore()
    [mid] = _seed(store, "gov_itest", 1)
    try:
        assert governance.forget(db_conn, mid) is True
        assert governance.forget(db_conn, mid) is False  # already gone
        rows = db_conn.execute("SELECT 1 FROM memory WHERE id = %s", (mid,)).fetchall()
        assert rows == []
    finally:
        db_conn.execute("DELETE FROM memory WHERE id = %s", (mid,))


def test_consolidate_compacts_old_into_one(
    db_conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        governance, "_summarize_old", lambda _c: "CONSOLIDATED higher-level summary"
    )
    monkeypatch.setattr("jarvis.models.router.embed", lambda _t: [0.1] * 768)
    store = PgVectorMemoryStore()
    seeded = _seed(store, "gov_itest", 6)  # 6 records of this kind
    new_id = None
    try:
        report = governance.consolidate(db_conn, kind="gov_itest", keep_recent=2)
        assert report["consolidated"] == 4  # 6 - 2 newest kept
        new_id = report["new_id"]
        assert report["summary"] == "CONSOLIDATED higher-level summary"
        # the 4 oldest are gone; 2 kept + 1 new consolidated remain
        remaining = db_conn.execute(
            "SELECT id FROM memory WHERE kind = 'gov_itest'"
        ).fetchall()
        remaining_ids = {r["id"] for r in remaining}
        assert new_id in remaining_ids
        assert len(remaining_ids) == 3  # 2 kept + 1 consolidated
        assert not (set(seeded[:4]) & remaining_ids)  # the 4 oldest were removed
        assert set(seeded[4:]) <= remaining_ids  # the 2 newest were kept
    finally:
        db_conn.execute("DELETE FROM memory WHERE kind = 'gov_itest'")
