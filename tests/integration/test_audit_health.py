"""5.5b integration: audit round-trip + health assembles against the live tunnel."""

from __future__ import annotations

import psycopg
import pytest

from jarvis.audit.log import list_audit, record

pytestmark = pytest.mark.integration


def test_audit_record_roundtrip(db_conn: psycopg.Connection) -> None:
    record(db_conn, actor="itest", action="mode.set", target="semi_autonomous", note="x")
    rows = list_audit(db_conn, 5)
    mine = [r for r in rows if r["actor"] == "itest" and r["action"] == "mode.set"]
    assert mine and mine[0]["target"] == "semi_autonomous"
    assert mine[0]["details"]["note"] == "x"
    db_conn.execute("DELETE FROM audit_log WHERE actor = 'itest'")


def test_health_reports_reachability_and_workers() -> None:
    from jarvis.ops.health import health

    h = health()
    assert set(h["reachable"]) == {"postgres", "redis", "ollama"}
    assert h["reachable"]["postgres"] is True  # tunnel is up for integration tests
    assert "selfcheck" in h["workers"]["expected"]
    assert isinstance(h["degraded"], bool)
