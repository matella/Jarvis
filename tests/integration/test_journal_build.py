"""P2 journaling integration: a seeded alert shows up in the timeline."""

from __future__ import annotations

from datetime import timedelta

import psycopg
import pytest

from jarvis import ids
from jarvis.core.journal import build_journal
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.repository import insert_event

pytestmark = pytest.mark.integration


def test_journal_includes_seeded_alert(db_conn: psycopg.Connection) -> None:
    suffix = ids.new_id("t").split("_")[1]
    ev = Event(
        type="container.oom_killed", severity=Severity.critical, source="docker",
        entity_ref=f"container:itest-{suffix}", occurred_at=utcnow() - timedelta(minutes=1),
        correlation_id=ids.new_id(ids.CORRELATION),
    )
    insert_event(db_conn, ev)
    try:
        entries = build_journal(db_conn, timedelta(hours=1))
        mine = [e for e in entries if e.ref == ev.id]
        assert len(mine) == 1
        assert mine[0].kind == "event" and mine[0].severity == "critical"
        # entries are chronologically sorted
        assert [e.ts for e in entries] == sorted(e.ts for e in entries)
    finally:
        db_conn.execute("DELETE FROM events WHERE id = %s", (ev.id,))
