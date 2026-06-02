"""Mail cache repository — upsert/triage/recent/important round-trip on a live DB (index=False)."""

from __future__ import annotations

from datetime import UTC, datetime

import psycopg
import pytest

from jarvis.mail import repository
from jarvis.mail.models import CachedMessage, Importance, Triage

pytestmark = pytest.mark.integration


def test_upsert_triage_and_accessors(db_conn: psycopg.Connection) -> None:
    db_conn.execute("DELETE FROM mail_cache")
    when = datetime(2026, 6, 2, 9, 0, tzinfo=UTC)
    m = CachedMessage(account="default", uid="1", from_addr="boss@co", subject="Deadline",
                      snippet="reply asap", received_at=when)
    repository.upsert(db_conn, m, index=False)

    repository.set_triage(db_conn, m.id, Triage(importance=Importance.high, needs_reply=True))
    got = repository.get(db_conn, m.id)
    assert got is not None and got.triage.importance is Importance.high

    # idempotent upsert on (account, uid) — re-sync doesn't duplicate
    repository.upsert(db_conn, m.model_copy(update={"subject": "Deadline (edited)"}), index=False)
    assert len(repository.recent(db_conn, account="default")) == 1

    assert [x.id for x in repository.important(db_conn)] == [m.id]
    assert repository.purge_account(db_conn, "default") == 1
    assert repository.recent(db_conn) == []
