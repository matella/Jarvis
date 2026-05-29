"""Phase-2 metrics integration: poll real docker stats (+GPU) into the metrics table."""

from __future__ import annotations

import psycopg
import pytest

from jarvis.ingest.metrics import ThresholdTracker, poll_once
from jarvis.ingest.metrics_store import latest_per_entity

pytestmark = pytest.mark.integration


def test_poll_once_writes_metrics(db_conn: psycopg.Connection) -> None:
    before = db_conn.execute("SELECT count(*) AS c FROM metrics").fetchone()["c"]
    try:
        result = poll_once(ThresholdTracker())
    except Exception as exc:  # noqa: BLE001
        if "connect" in str(exc).lower():
            pytest.skip(f"docker/ssh unavailable — {exc}")
        raise

    assert result["containers"] >= 1  # at least jarvis-postgres/redis are running
    after = db_conn.execute("SELECT count(*) AS c FROM metrics").fetchone()["c"]
    assert after > before

    rows = latest_per_entity(db_conn, kind="container")
    assert rows
    sample = rows[0]["sample"]
    assert "cpu_pct" in sample and "mem_pct" in sample
