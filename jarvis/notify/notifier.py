"""Notifier — a rules-based consumer that pushes notify-worthy events to the channel.

A second consumer group on the event spine (per M2's design). Deterministic: notifies on
correlated incidents and individual critical events, with a per-(type,entity) cooldown to
avoid storms. Read-only on the spine — it acks every message but writes nothing.
"""

from __future__ import annotations

import os
import socket
import time
from dataclasses import dataclass, field

import redis

from jarvis.config import get_settings
from jarvis.events.models import Event
from jarvis.events.stream import ensure_group, get_redis
from jarvis.notify.channel import send

_NOTIFY_TYPES = {"incident.correlated"}


def should_notify(event: Event) -> bool:
    return event.severity.value == "critical" or event.type in _NOTIFY_TYPES


def _format(event: Event) -> tuple[str, str, str]:
    if event.type == "incident.correlated":
        title = f"Incident: {event.payload.get('summary', 'correlated alerts')}"
        message = str(event.payload.get("root_cause") or "")
        return title, message, "high"
    title = f"{event.severity.value.upper()}: {event.type}"
    message = f"{event.entity_ref or ''} {event.payload}".strip()
    return title, message, "urgent"


@dataclass
class NotifierState:
    cooldown_s: int
    _last: dict[tuple[str, str | None], float] = field(default_factory=dict)

    def allow(self, key: tuple[str, str | None], now: float) -> bool:
        last = self._last.get(key)
        if last is not None and now - last < self.cooldown_s:
            return False
        self._last[key] = now
        return True


def process_batch(
    r: redis.Redis, *, stream: str, group: str, consumer: str, state: NotifierState,
    count: int = 10, block_ms: int = 1000,
) -> int:
    resp = r.xreadgroup(group, consumer, {stream: ">"}, count=count, block=block_ms)
    notified = 0
    for _stream, messages in resp or []:
        for msg_id, fields in messages:
            try:
                event = Event.model_validate_json(fields["data"])
                key = (event.type, event.entity_ref)
                if should_notify(event) and state.allow(key, time.monotonic()):
                    title, message, priority = _format(event)
                    send(
                        title=title, message=message, priority=priority,
                        event_type=event.type, entity=event.entity_ref,
                        severity=event.severity.value,
                    )
                    notified += 1
            except Exception:  # noqa: BLE001 — never let one bad message stall notifications
                pass
            r.xack(stream, group, msg_id)
    return notified


def run_notifier(*, once: bool = False) -> None:
    s = get_settings()
    r = get_redis()
    consumer = f"{socket.gethostname()}-{os.getpid()}"
    ensure_group(r, s.events_stream, s.notify_group, start_id="$")  # only new events
    state = NotifierState(s.notify_cooldown_s)
    while True:
        notified = process_batch(
            r, stream=s.events_stream, group=s.notify_group, consumer=consumer, state=state
        )
        if once:
            return
        if notified == 0:
            time.sleep(0.5)
