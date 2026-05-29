"""Redis Streams helpers — the event spine's transport.

Thin wrappers over redis-py: a client factory, idempotent consumer-group creation, event
publish (capped stream), and DLQ publish. Stream/group names default from settings but are
passable so tests can run against isolated streams.
"""

from __future__ import annotations

import redis

from jarvis.config import get_settings
from jarvis.events.models import Event


def get_redis() -> redis.Redis:
    s = get_settings()
    return redis.Redis(
        host=s.redis_host,
        port=s.redis_port,
        db=s.redis_db,
        decode_responses=True,
    )


def ensure_group(r: redis.Redis, stream: str, group: str, start_id: str = "0") -> None:
    """Create the consumer group (and the stream) if absent; no-op if it exists.

    start_id="0" replays all history (the projector must); "$" starts at new events only
    (the notifier — don't page about historical incidents on first start).
    """
    try:
        r.xgroup_create(stream, group, id=start_id, mkstream=True)
    except redis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def publish_event(
    r: redis.Redis, event: Event, *, stream: str | None = None, maxlen: int | None = None
) -> str:
    s = get_settings()
    return r.xadd(
        stream or s.events_stream,
        {"data": event.model_dump_json()},
        maxlen=maxlen if maxlen is not None else s.stream_maxlen,
        approximate=True,
    )


def emit_event(event: Event) -> None:
    """Best-effort publish for telemetry events; never raises (must not break callers)."""
    try:
        publish_event(get_redis(), event)
    except Exception:
        pass


def publish_dlq(
    r: redis.Redis,
    *,
    data: str,
    failure_class: str,
    error: str,
    original_id: str,
    stream: str | None = None,
) -> str:
    s = get_settings()
    return r.xadd(
        stream or s.dlq_stream,
        {
            "data": data,
            "failure_class": failure_class,
            "error": error,
            "original_id": original_id,
        },
    )
