"""Post-game brief — `hots.match_completed` → a short French notification.

A third consumer group on the event spine (alongside the projector and the notifier). When a HotS
match lands, it formats a one-line brief from the operator's perspective ("Défaite sur Silver City
— Muradin 2/18/1") and pushes it to the notify channel. Read-only on the spine: acks every message,
writes nothing. The group starts at "$" so enabling it never replays the backfilled history.

"Me" is identified by `hots_player_name` (in-game name). Empty or not found → a generic
match-result brief so the worker still says something useful.
"""

from __future__ import annotations

import os
import socket
import time

import redis

from jarvis.config import get_settings
from jarvis.events.models import Event
from jarvis.events.stream import ensure_group, get_redis
from jarvis.notify.channel import send

_MODE_NAMES = {
    50001: "Quick Match",
    50021: "vs IA",
    50031: "Brawl",
    50051: "Unranked Draft",
    50061: "Hero League",
    50071: "Team League",
    50091: "Storm League",
}


def _find_me(players: list[dict], name: str) -> dict | None:
    if not name:
        return None
    target = name.casefold()
    return next((p for p in players if str(p.get("name", "")).casefold() == target), None)


def format_brief(event: Event, player_name: str) -> tuple[str, str, str] | None:
    """(title, message, priority) for a match event, or None if it isn't one."""
    if event.type != "hots.match_completed":
        return None
    p = event.payload
    map_name = p.get("map") or "carte inconnue"
    mode = _MODE_NAMES.get(p.get("mode"), "")
    players = p.get("players") or []
    me = _find_me(players, player_name)

    if me is not None:
        won = bool(me.get("win"))
        result = "Victoire" if won else "Défaite"
        hero = me.get("hero") or "?"
        kda = me.get("kda") or {}
        kills = int(kda.get("kills") or 0)
        deaths = int(kda.get("deaths") or 0)
        takedowns = int(kda.get("takedowns") or 0)
        assists = max(0, takedowns - kills)
        emoji = "🏆" if won else "💀"
        suffix = f" · {mode}" if mode else ""
        return (
            f"{emoji} HotS — {result}",
            f"{hero} sur {map_name} — {kills}/{assists}/{deaths}{suffix}",
            "default" if won else "high",
        )

    # générique : on ne sait pas qui est l'opérateur
    winner = p.get("winner")
    side = {0: "équipe bleue", 1: "équipe rouge"}.get(winner, "—")
    return ("🎮 HotS — partie terminée", f"{map_name} — {side} gagne", "low")


def process_batch(
    r: redis.Redis, *, stream: str, group: str, consumer: str, player_name: str,
    count: int = 10, block_ms: int = 1000,
) -> int:
    resp = r.xreadgroup(group, consumer, {stream: ">"}, count=count, block=block_ms)
    sent = 0
    for _stream, messages in resp or []:
        for msg_id, fields in messages:
            try:
                event = Event.model_validate_json(fields["data"])
                brief = format_brief(event, player_name)
                if brief is not None:
                    title, message, priority = brief
                    send(
                        title=title, message=message, priority=priority,
                        event_type=event.type, entity=event.entity_ref,
                    )
                    print(f"[hots_brief] {title} — {message}", flush=True)
                    sent += 1
            except Exception:  # noqa: BLE001 — one bad message must not stall briefs
                pass
            r.xack(stream, group, msg_id)
    return sent


def run_hots_brief(*, once: bool = False) -> None:
    s = get_settings()
    r = get_redis()
    consumer = f"{socket.gethostname()}-{os.getpid()}"
    ensure_group(r, s.events_stream, s.hots_brief_group, start_id="$")  # new matches only
    while True:
        sent = process_batch(
            r, stream=s.events_stream, group=s.hots_brief_group, consumer=consumer,
            player_name=s.hots_player_name,
        )
        if once:
            return
        if sent == 0:
            time.sleep(0.5)
