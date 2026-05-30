"""Inbox triage — summarize + classify inbound content (mail/feeds), push only what matters.

A SECOND notification path, distinct from the deterministic system notifier: this one reasons.
For each `mail.received` / `feed.item` event it runs ONE inference → {importance, summary}, and
pushes via the shared channel only when importance clears the configured floor (the noise gate) —
the rest stay on the spine for a digest. Content is wrapped as untrusted data: a phishing/clickbait
body can shape a summary, never an instruction. Degrades cleanly when the LLM is down (skips, never
crashes); its own consumer group starts at `$` so it never replays history.
"""

from __future__ import annotations

import json
import os
import socket
import time

import redis

from jarvis.config import get_settings
from jarvis.core.degrade import reasoning_available
from jarvis.events.models import Event
from jarvis.events.stream import ensure_group, get_redis
from jarvis.notify.channel import send
from jarvis.security.sanitize import wrap_untrusted

TRIAGE_TYPES = {"mail.received", "feed.item"}
TRIAGE_GROUP = "jarvis:triage"
_RANK = {"low": 0, "normal": 1, "high": 2}

_TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "importance": {"type": "string", "enum": ["high", "normal", "low"]},
        "summary": {"type": "string"},
    },
    "required": ["importance", "summary"],
}


def should_push(importance: str, *, floor: str) -> bool:
    """Pure: push only items whose importance is at or above the configured floor."""
    return _RANK.get(importance, 1) >= _RANK.get(floor, 2)


def _content(event: Event) -> tuple[str, str]:
    """(notification title, raw untrusted content to summarize) for a mail/feed event."""
    p = event.payload
    if event.type == "mail.received":
        title = f"📬 {p.get('account', 'mail')}: {p.get('subject', '(no subject)')}"
        body = f"From: {p.get('from', '')}\nSubject: {p.get('subject', '')}\n{p.get('snippet', '')}"
        return title, body
    title = f"📰 {p.get('title', 'feed item')}"
    return title, f"{p.get('title', '')}\n{p.get('summary', '')}"


def triage_item(event: Event) -> tuple[str, str]:
    """One inference → (importance, summary). Content is framed as untrusted data."""
    from jarvis.models.scheduler import Priority
    from jarvis.models.scheduler import chat as sched_chat

    _title, body = _content(event)
    kind = "email" if event.type == "mail.received" else "news/feed item"
    prompt = (
        f"You triage an operator's inbound {kind}. Reply with ONE JSON object: "
        '{"importance": "high"|"normal"|"low", "summary": <one short sentence>}. '
        "high = needs attention soon (personal, time-sensitive, action required, security/billing);"
        " normal = useful but not urgent; low = newsletter/marketing/automated notice.\n\n"
        + wrap_untrusted(body)
    )
    resp = sched_chat(
        "reasoning", [{"role": "user", "content": prompt}],
        priority=Priority.BACKGROUND, format=_TRIAGE_SCHEMA,
    )
    try:
        data = json.loads(str(resp["message"]["content"]))
        return str(data.get("importance", "normal")), str(data.get("summary", "")).strip()
    except (json.JSONDecodeError, TypeError):
        return "normal", ""


def process_batch(
    r: redis.Redis, *, stream: str, group: str, consumer: str, floor: str,
    count: int = 10, block_ms: int = 1000,
) -> int:
    resp = r.xreadgroup(group, consumer, {stream: ">"}, count=count, block=block_ms)
    pushed = 0
    for _stream, messages in resp or []:
        for msg_id, fields in messages:
            try:
                event = Event.model_validate_json(fields["data"])
                if event.type in TRIAGE_TYPES and reasoning_available():
                    importance, summary = triage_item(event)
                    if should_push(importance, floor=floor):
                        title, _body = _content(event)
                        prio = "high" if importance == "high" else "default"
                        send(title=title, message=summary or title, priority=prio,
                             event_type=event.type, importance=importance)
                        pushed += 1
            except Exception:  # noqa: BLE001 — never let one bad message stall triage
                pass
            r.xack(stream, group, msg_id)
    return pushed


def run_triage(*, once: bool = False) -> None:
    s = get_settings()
    r = get_redis()
    consumer = f"{socket.gethostname()}-{os.getpid()}"
    ensure_group(r, s.events_stream, TRIAGE_GROUP, start_id="$")  # only new content
    while True:
        pushed = process_batch(
            r, stream=s.events_stream, group=TRIAGE_GROUP, consumer=consumer,
            floor=s.triage_min_importance,
        )
        if once:
            return
        if pushed == 0:
            time.sleep(0.5)
