"""Event stream consumer — Redis Stream → `events` table → state projector.

At-least-once consumer group. Each message is processed in one DB transaction
(insert_event → project); on success it is XACK'd. Failures stay in the pending list and
are retried via XCLAIM until `max_deliveries`, after which they are routed to the DLQ stream
(tagged with a typed `failure_class`) and acked. No model is involved.
"""

from __future__ import annotations

import os
import socket
import time
from dataclasses import dataclass

import psycopg
import redis
from pydantic import ValidationError

from jarvis import db
from jarvis.config import get_settings
from jarvis.events.models import Event
from jarvis.events.repository import insert_event
from jarvis.events.stream import ensure_group, get_redis, publish_dlq
from jarvis.state.projector import project


@dataclass
class ConsumerConfig:
    stream: str
    group: str
    consumer: str
    dlq_stream: str
    max_deliveries: int
    retry_idle_ms: int = 5_000
    read_count: int = 10
    block_ms: int = 1_000


def default_config() -> ConsumerConfig:
    s = get_settings()
    return ConsumerConfig(
        stream=s.events_stream,
        group=s.consumer_group,
        consumer=f"{socket.gethostname()}-{os.getpid()}",
        dlq_stream=s.dlq_stream,
        max_deliveries=s.max_deliveries,
    )


def _classify(exc: Exception) -> str:
    if isinstance(exc, (ValidationError, ValueError)):
        return "validation_failure"
    return "unknown"


def _handle(conn: psycopg.Connection, fields: dict) -> None:
    """Parse → insert → project, atomically. Raises on any failure."""
    event = Event.model_validate_json(fields["data"])
    with conn.transaction():
        insert_event(conn, event)
        project(conn, event)


def process_new(r: redis.Redis, conn: psycopg.Connection, cfg: ConsumerConfig) -> int:
    resp = r.xreadgroup(
        cfg.group, cfg.consumer, {cfg.stream: ">"}, count=cfg.read_count, block=cfg.block_ms
    )
    processed = 0
    for _stream, messages in resp or []:
        for msg_id, fields in messages:
            try:
                _handle(conn, fields)
                r.xack(cfg.stream, cfg.group, msg_id)
                processed += 1
            except Exception:
                pass  # stays pending; process_pending owns retry/DLQ
    return processed


def process_pending(
    r: redis.Redis, conn: psycopg.Connection, cfg: ConsumerConfig
) -> dict[str, int]:
    retried = 0
    dead = 0
    pending = r.xpending_range(cfg.stream, cfg.group, min="-", max="+", count=100)
    for entry in pending:
        msg_id = entry["message_id"]
        delivered = entry["times_delivered"]
        idle = entry["time_since_delivered"]

        if delivered > cfg.max_deliveries:
            rows = r.xrange(cfg.stream, min=msg_id, max=msg_id, count=1)
            fields = rows[0][1] if rows else {}
            failure_class = "unknown"
            error = f"exceeded max_deliveries={cfg.max_deliveries}"
            try:
                _handle(conn, fields)  # one last attempt to capture a typed failure
                r.xack(cfg.stream, cfg.group, msg_id)
                retried += 1
                continue
            except Exception as exc:
                failure_class = _classify(exc)
                error = f"{type(exc).__name__}: {exc}"
            publish_dlq(
                r,
                data=fields.get("data", ""),
                failure_class=failure_class,
                error=error,
                original_id=msg_id,
                stream=cfg.dlq_stream,
            )
            r.xack(cfg.stream, cfg.group, msg_id)
            dead += 1
        elif idle >= cfg.retry_idle_ms:
            claimed = r.xclaim(
                cfg.stream, cfg.group, cfg.consumer,
                min_idle_time=cfg.retry_idle_ms, message_ids=[msg_id],
            )
            for claimed_id, fields in claimed:
                try:
                    _handle(conn, fields)
                    r.xack(cfg.stream, cfg.group, claimed_id)
                    retried += 1
                except Exception:
                    pass
    return {"retried": retried, "dead": dead}


def run_batch(r: redis.Redis, conn: psycopg.Connection, cfg: ConsumerConfig) -> dict[str, int]:
    processed = process_new(r, conn, cfg)
    pending = process_pending(r, conn, cfg)
    return {"processed": processed, **pending}


def run_once(
    cfg: ConsumerConfig | None = None,
    *,
    r: redis.Redis | None = None,
    conn: psycopg.Connection | None = None,
) -> dict[str, int]:
    cfg = cfg or default_config()
    r = r or get_redis()
    ensure_group(r, cfg.stream, cfg.group)
    if conn is not None:
        return run_batch(r, conn, cfg)
    with db.connect(autocommit=True) as owned:
        return run_batch(r, owned, cfg)


def run_forever(cfg: ConsumerConfig | None = None) -> None:
    cfg = cfg or default_config()
    r = get_redis()
    ensure_group(r, cfg.stream, cfg.group)
    with db.connect(autocommit=True) as conn:
        while True:
            result = run_batch(r, conn, cfg)
            if not any(result.values()):
                time.sleep(0.5)
            elif result["processed"] or result["dead"]:
                print(
                    f"processed={result['processed']} retried={result['retried']} "
                    f"dlq={result['dead']}"
                )
