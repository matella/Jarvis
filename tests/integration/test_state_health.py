"""Consolidation integration: metric signal events reflect into state.attrs health."""

from __future__ import annotations

import psycopg
import pytest

from jarvis import ids
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.repository import insert_event
from jarvis.state.projector import project

pytestmark = pytest.mark.integration


def test_cpu_high_signal_sets_health_attr(db_conn: psycopg.Connection) -> None:
    suffix = ids.new_id("t").split("_")[1]
    entity = f"container:itest-{suffix}"
    try:
        # lifecycle event first → status running
        started = Event(
            type="container.started", severity=Severity.info, source="docker",
            entity_ref=entity, occurred_at=utcnow(), payload={"image": "alpine"},
            correlation_id=ids.new_id(ids.CORRELATION),
        )
        insert_event(db_conn, started)
        assert project(db_conn, started) is True

        # metric signal → sets cpu_status without touching lifecycle status
        cpu = Event(
            type="container.cpu_high", severity=Severity.warning, source="metrics",
            entity_ref=entity, occurred_at=utcnow(),
            payload={"metric": "cpu", "value": 99.0, "threshold": 85.0},
            correlation_id=ids.new_id(ids.CORRELATION),
        )
        insert_event(db_conn, cpu)
        assert project(db_conn, cpu) is True

        row = db_conn.execute(
            "SELECT status, attrs FROM state WHERE entity = %s AND kind = 'container'",
            (entity,),
        ).fetchone()
        assert row is not None
        assert row["status"] == "running"          # lifecycle untouched
        assert row["attrs"]["cpu_status"] == "high"  # health reflected
    finally:
        db_conn.execute("DELETE FROM state WHERE entity = %s", (entity,))
        db_conn.execute("DELETE FROM events WHERE entity_ref = %s", (entity,))
