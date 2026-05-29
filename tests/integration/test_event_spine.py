"""M2 acceptance: stream → consumer → events table + state projection, and the DLQ path.

Uses isolated per-test stream/group names so it never touches the production spine, and
deletes the test stream afterward.
"""

from __future__ import annotations

import psycopg
import pytest
import redis as redis_lib

from jarvis import ids
from jarvis.events.consumer import ConsumerConfig, run_batch
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import ensure_group, publish_event

pytestmark = pytest.mark.integration


def _cfg(suffix: str) -> ConsumerConfig:
    return ConsumerConfig(
        stream=f"jarvis:test:events:{suffix}",
        group="jarvis:test:projectors",
        consumer="test-consumer",
        dlq_stream=f"jarvis:test:dlq:{suffix}",
        max_deliveries=1,
        retry_idle_ms=0,  # retry immediately so the test doesn't wait
        block_ms=100,
    )


def test_event_flows_to_table_and_state(
    db_conn: psycopg.Connection, redis_client: redis_lib.Redis
) -> None:
    suffix = ids.new_id("t").split("_")[1]
    cfg = _cfg(suffix)
    entity = f"container:itest-{suffix}"
    ensure_group(redis_client, cfg.stream, cfg.group)

    event = Event(
        type="container.started",
        severity=Severity.info,
        source="docker",
        entity_ref=entity,
        occurred_at=utcnow(),
        payload={"image": "alpine:latest", "action": "start"},
        correlation_id=ids.new_id(ids.CORRELATION),
    )
    try:
        publish_event(redis_client, event, stream=cfg.stream, maxlen=1000)

        result = run_batch(redis_client, db_conn, cfg)
        assert result["processed"] == 1

        # Event landed in the append-only log.
        row = db_conn.execute("SELECT type FROM events WHERE id = %s", (event.id,)).fetchone()
        assert row is not None and row["type"] == "container.started"

        # State projection updated.
        state = db_conn.execute(
            "SELECT status, attrs, last_event_id FROM state "
            "WHERE entity = %s AND kind = 'container'",
            (entity,),
        ).fetchone()
        assert state is not None
        assert state["status"] == "running"
        assert state["attrs"]["image"] == "alpine:latest"
        assert state["last_event_id"] == event.id

        # Message was acked — nothing left pending.
        pending = redis_client.xpending(cfg.stream, cfg.group)
        assert pending["pending"] == 0
    finally:
        db_conn.execute("DELETE FROM events WHERE id = %s", (event.id,))
        db_conn.execute("DELETE FROM state WHERE entity = %s", (entity,))
        redis_client.delete(cfg.stream)


def test_poison_message_goes_to_dlq(
    db_conn: psycopg.Connection, redis_client: redis_lib.Redis
) -> None:
    suffix = ids.new_id("t").split("_")[1]
    cfg = _cfg(suffix)
    ensure_group(redis_client, cfg.stream, cfg.group)

    try:
        # Unparseable body — fails Event validation on every attempt.
        redis_client.xadd(cfg.stream, {"data": "not-json"})

        # First batch: delivered=1 (not yet over max), claimed to delivered=2.
        # Second batch: delivered>max_deliveries=1 → routed to DLQ + acked.
        for _ in range(3):
            run_batch(redis_client, db_conn, cfg)
            if redis_client.xlen(cfg.dlq_stream) > 0:
                break

        assert redis_client.xlen(cfg.dlq_stream) == 1
        _stream_id, fields = redis_client.xrange(cfg.dlq_stream)[0]
        assert fields["failure_class"] == "validation_failure"
        assert fields["data"] == "not-json"

        pending = redis_client.xpending(cfg.stream, cfg.group)
        assert pending["pending"] == 0
    finally:
        redis_client.delete(cfg.stream)
        redis_client.delete(cfg.dlq_stream)
