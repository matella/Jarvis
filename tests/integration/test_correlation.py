"""P2 alert-correlation integration: seed an alert burst → one linked incident."""

from __future__ import annotations

from datetime import timedelta

import psycopg
import pytest

from jarvis import ids
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.repository import insert_event

pytestmark = pytest.mark.integration


def test_correlate_groups_burst_into_incident(db_conn: psycopg.Connection) -> None:
    from jarvis.agents.correlator import correlate
    from jarvis.core.context_store import get_context

    suffix = ids.new_id("t").split("_")[1]
    base = utcnow() - timedelta(minutes=5)
    seeded = []
    for i in range(3):
        ev = Event(
            type="container.died", severity=Severity.warning, source="docker",
            entity_ref=f"container:itest-{suffix}-{i}",
            occurred_at=base + timedelta(seconds=i * 10),
            payload={"exit_code": 137}, correlation_id=ids.new_id(ids.CORRELATION),
        )
        insert_event(db_conn, ev)
        seeded.append(ev.id)

    incident_ids: list[str] = []
    try:
        try:
            incidents = correlate(timedelta(hours=1))
        except Exception as exc:  # noqa: BLE001
            if "connect" in str(exc).lower():
                pytest.skip(f"Ollama unavailable — {exc}")
            raise

        # Find the incident covering our seeded burst.
        mine = [i for i in incidents if set(seeded) & set(i.event_ids)]
        assert len(mine) == 1
        inc = mine[0]
        incident_ids.append(inc.incident_id)
        assert set(seeded).issubset(set(inc.event_ids))
        assert inc.event_count >= 3
        assert inc.severity is Severity.warning
        assert inc.summary
        # provenance stored
        assert inc.context_ref and get_context(db_conn, inc.context_ref) is not None
        # persisted
        row = db_conn.execute(
            "SELECT count(*) AS c FROM incidents WHERE incident_id = %s", (inc.incident_id,)
        ).fetchone()
        assert row["c"] == 1
    finally:
        for iid in incident_ids:
            db_conn.execute("DELETE FROM incidents WHERE incident_id = %s", (iid,))
        db_conn.execute("DELETE FROM events WHERE id = ANY(%s)", (seeded,))
