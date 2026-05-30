"""Ambient reactor — Jarvis acts on its own perception.

A spine consumer that, on a qualifying operational event, auto-runs ONE cognition step: the
infrastructure agent proposes a GATED intent. This closes the cognition loop (event → reasoning
→ proposed intent), but adds no execution power — every proposal still flows through the M4
approval+mode gate, and under observe nothing runs. Loop-safe: it reacts only to operational
events, never to Jarvis's own (so proposing can't trigger more proposing).
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

_TRIGGER_TYPES = {"container.died", "container.oom_killed"}
# React only to genuine operational signals — never Jarvis's own cognition events, so an
# auto-proposed intent (source=infrastructure_agent) can't trigger another reaction.
_OPERATIONAL_SOURCES = {"docker", "metrics"}


def should_react(event: Event) -> bool:
    return (
        event.source in _OPERATIONAL_SOURCES
        and event.type in _TRIGGER_TYPES
        and event.entity_ref is not None
    )


@dataclass
class ReactorState:
    cooldown_s: int
    _last: dict[str, float] = field(default_factory=dict)

    def allow(self, entity: str, now: float) -> bool:
        last = self._last.get(entity)
        if last is not None and now - last < self.cooldown_s:
            return False
        self._last[entity] = now
        return True


def process_batch(
    r: redis.Redis, *, stream: str, group: str, consumer: str, state: ReactorState,
    count: int = 10, block_ms: int = 1000,
) -> int:
    from jarvis import db
    from jarvis.agents.infrastructure import propose_intent
    from jarvis.core.modes import Mode, get_mode
    from jarvis.intents import service

    with db.connect() as conn:
        mode = get_mode(conn)

    resp = r.xreadgroup(group, consumer, {stream: ">"}, count=count, block=block_ms)
    reacted = 0
    for _stream, messages in resp or []:
        for msg_id, fields in messages:
            try:
                event = Event.model_validate_json(fields["data"])
                # maintenance suspends the reactor (still drain so the stream doesn't pile up).
                if (
                    mode is not Mode.maintenance
                    and should_react(event)
                    and state.allow(event.entity_ref, time.monotonic())
                ):
                    from jarvis.core.degrade import defer, reasoning_available

                    # Graceful degradation: if the LLM is down, defer the proposal (the drain
                    # worker replays it) instead of crashing the reaction.
                    if not reasoning_available():
                        with db.connect(autocommit=True) as conn:
                            defer(conn, "infra_propose", {"entity": event.entity_ref})
                        print(f"[reactor] reasoning down — deferred {event.entity_ref}", flush=True)
                        r.xack(stream, group, msg_id)
                        continue
                    intent = propose_intent(event.entity_ref)
                    reacted += 1
                    print(
                        f"[reactor] {event.type} {event.entity_ref} → proposed "
                        f"{intent.type} ({intent.intent_id})",
                        flush=True,
                    )
                    # semi_autonomous: the gate auto-runs it if low-risk+reversible, else holds
                    # for approval — the mode policy decides, not the reactor.
                    if mode is Mode.semi_autonomous:
                        from jarvis.core.governance import frozen_now
                        if frozen_now():
                            print("[reactor] held — freeze window active", flush=True)
                            r.xack(stream, group, msg_id)
                            continue
                        from jarvis.audit.log import record
                        with db.connect(autocommit=True) as conn:
                            try:
                                ex = service.execute(conn, intent.intent_id)
                                record(conn, actor="reactor", action="intent.execute",
                                       target=intent.intent_id, outcome=ex.outcome.value)
                                print(f"[reactor] auto-executed → {ex.outcome.value}", flush=True)
                            except service.ApprovalRequired:
                                print("[reactor] held for approval (not auto-safe)", flush=True)
            except Exception as exc:  # noqa: BLE001 — one bad reaction must not stall the loop
                print(f"[reactor] reaction failed: {exc!r}", flush=True)
            r.xack(stream, group, msg_id)
    return reacted


def run_reactor(*, once: bool = False) -> None:
    s = get_settings()
    if not s.reactor_enabled:
        print("[reactor] disabled (reactor_enabled=false)", flush=True)
        return
    r = get_redis()
    consumer = f"{socket.gethostname()}-{os.getpid()}"
    ensure_group(r, s.events_stream, s.reactor_group, start_id="$")  # only new events
    state = ReactorState(s.reactor_cooldown_s)
    while True:
        reacted = process_batch(
            r, stream=s.events_stream, group=s.reactor_group, consumer=consumer, state=state
        )
        if once:
            return
        if reacted == 0:
            time.sleep(0.5)
