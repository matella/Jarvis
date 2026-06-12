"""Storm Codex match results → Jarvis events.

`storm-codex-server` PUBLISHes a domain message on a Redis pub/sub channel when a replay finishes
parsing (end of a HotS game). This bridge subscribes, validates/translates it into a spine `Event`
(`hots.match_completed`), and publishes it into the event stream — so match outcomes become
first-class facts in Jarvis's append-only log (queryable, brief-able).

Decoupling on purpose: storm-codex is its own open-source service and owns its message shape;
this module is the boundary that adapts it to Jarvis's `Event` contract (the spine validates here,
per the CLAUDE.md "schema-validated at every boundary" rule). Pub/sub is fire-and-forget — a
missed brief while the daemon is down is acceptable (the match itself is durably stored by
storm-codex), so no consumer group is needed on this hop.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from jarvis import ids
from jarvis.config import get_settings
from jarvis.events.models import Event, Severity
from jarvis.events.stream import get_redis, publish_event


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(UTC)


def to_event(msg: dict) -> Event | None:
    """storm-codex domain message → spine `Event`. None if it carries no match id."""
    data = msg.get("data") if isinstance(msg.get("data"), dict) else msg
    match_id = data.get("match_id")
    if match_id is None:
        return None
    return Event(
        type="hots.match_completed",
        severity=Severity.info,
        source="storm-codex",
        entity_ref=f"hots-match:{match_id}",
        occurred_at=_parse_dt(msg.get("occurred_at") or data.get("occurred_at")),
        correlation_id=str(msg.get("correlation_id") or ids.new_id(ids.CORRELATION)),
        payload={
            "match_id": match_id,
            "map": data.get("map"),
            "mode": data.get("mode"),
            "length": data.get("length"),
            "winner": data.get("winner"),
            "players": data.get("players", []),
        },
    )


def run_hots_match_ingester(once: bool = False) -> None:
    """Subscribe to the storm-codex channel and bridge each match message into the spine.

    `once=True` processes a single message (or returns after a short idle) — for `--once` tests.
    """
    s = get_settings()
    r = get_redis()
    pubsub = r.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe(s.storm_codex_match_channel)
    print(f"[hots_matches] subscribed to {s.storm_codex_match_channel}", flush=True)

    while True:
        raw = pubsub.get_message(timeout=5.0)
        if raw is None:
            if once:
                return
            continue
        if raw.get("type") != "message":
            continue
        try:
            event = to_event(json.loads(raw["data"]))
            if event is not None:
                publish_event(r, event)
                print(f"[hots_matches] match {event.payload['match_id']} → spine", flush=True)
        except Exception as exc:  # noqa: BLE001 — never let one bad message kill the bridge
            print(f"[hots_matches] bad message dropped: {exc!r}", flush=True)
        if once:
            return
