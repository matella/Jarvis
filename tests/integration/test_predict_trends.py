"""P5 predictive integration: rising metric samples produce a trend prediction."""

from __future__ import annotations

from datetime import timedelta

import psycopg
import pytest
from psycopg.types.json import Json

from jarvis import ids
from jarvis.events.models import utcnow
from jarvis.ingest.predict import TrendTracker, detect_trends

pytestmark = pytest.mark.integration


def test_rising_memory_predicts_trend(db_conn: psycopg.Connection) -> None:
    entity = f"container:itest-{ids.new_id('t').split('_')[1]}"
    base = utcnow() - timedelta(minutes=10)
    try:
        # climbing mem_pct (60 → ~84 over 8 min), threshold 90 → should project a crossing soon
        for i in range(8):
            sample = {"cpu_pct": 5.0, "mem_pct": 60.0 + i * 3.5}
            db_conn.execute(
                "INSERT INTO metrics (entity, kind, sample, ts) VALUES (%s, 'container', %s, %s)",
                (entity, Json(sample), base + timedelta(minutes=i)),
            )

        preds = detect_trends(db_conn, TrendTracker())
        mine = [p for p in preds if p["entity"] == entity and p["metric"] == "mem_pct"]
        assert len(mine) == 1
        assert mine[0]["type"] == "container.memory_trending"
        assert mine[0]["eta_minutes"] > 0
    finally:
        db_conn.execute("DELETE FROM metrics WHERE entity = %s", (entity,))


def test_flat_metric_predicts_nothing(db_conn: psycopg.Connection) -> None:
    entity = f"container:itest-{ids.new_id('t').split('_')[1]}"
    base = utcnow() - timedelta(minutes=10)
    try:
        for i in range(8):  # flat mem_pct → no trend
            db_conn.execute(
                "INSERT INTO metrics (entity, kind, sample, ts) VALUES (%s, 'container', %s, %s)",
                (entity, Json({"cpu_pct": 5.0, "mem_pct": 40.0}), base + timedelta(minutes=i)),
            )
        preds = detect_trends(db_conn, TrendTracker())
        assert not [p for p in preds if p["entity"] == entity]
    finally:
        db_conn.execute("DELETE FROM metrics WHERE entity = %s", (entity,))
