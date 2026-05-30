"""5.5a integration: a state snapshot + replay rebuilds the projection exactly."""

from __future__ import annotations

import psycopg
import pytest

from jarvis import ids
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.repository import insert_event
from jarvis.state.projector import project
from jarvis.state.snapshotter import rebuild_state, write_snapshot

pytestmark = pytest.mark.integration


def test_snapshot_then_rebuild_reproduces_state(db_conn: psycopg.Connection) -> None:
    entity = f"container:itest-snap-{ids.new_id('t').split('_')[1]}"

    def _ev(etype: str) -> Event:
        return Event(type=etype, severity=Severity.info, source="docker", entity_ref=entity,
                     occurred_at=utcnow(), payload={"image": "alpine"},
                     correlation_id=ids.new_id(ids.CORRELATION))

    started = _ev("container.started")
    insert_event(db_conn, started)
    project(db_conn, started)  # state: running

    snap_id = write_snapshot(db_conn)  # checkpoint at "running"

    # a later event after the snapshot
    died = _ev("container.died")
    insert_event(db_conn, died)
    project(db_conn, died)  # state: exited

    before = db_conn.execute(
        "SELECT status, last_event_id FROM state WHERE entity = %s", (entity,)
    ).fetchone()
    try:
        assert snap_id.startswith("snap_")
        assert before["status"] == "exited"

        # blow away state, rebuild from snapshot + replay → must reproduce "exited"
        rebuild_state(db_conn)
        after = db_conn.execute(
            "SELECT status, last_event_id FROM state WHERE entity = %s", (entity,)
        ).fetchone()
        assert after is not None
        assert after["status"] == before["status"] == "exited"
        assert after["last_event_id"] == before["last_event_id"]
    finally:
        db_conn.execute("DELETE FROM events WHERE entity_ref = %s", (entity,))
        db_conn.execute("DELETE FROM state WHERE entity = %s", (entity,))
        db_conn.execute("DELETE FROM snapshots WHERE id = %s", (snap_id,))
