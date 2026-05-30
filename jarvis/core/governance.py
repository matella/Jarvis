"""Governance polish (backlog #9) — change windows, universal preview, proactive nudges.

Three guardrails on top of the mode gate:
- **freeze windows**: autonomous actions (reactor / plan executor) are denied during configured
  windows (e.g. business hours) — a human-approved action still goes through, but Jarvis won't act
  on its own when you've said "not now". Pure `is_frozen_now`.
- **universal preview**: any mutating tool can describe what it *would* change (`Tool.preview`),
  surfaced before approval — generalizing the code-edit diff to every capability.
- **proactive nudges**: when proposals pile up unapproved, emit a `governance.nudge` so they don't
  rot silently.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import psycopg

from jarvis import ids
from jarvis.config import get_settings
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import emit_event


def _in_window(now_hm: int, start_hm: int, end_hm: int) -> bool:
    # minutes-since-midnight; supports windows that wrap past midnight (start > end)
    if start_hm <= end_hm:
        return start_hm <= now_hm < end_hm
    return now_hm >= start_hm or now_hm < end_hm


def is_frozen_now(now: datetime, windows: list[str]) -> bool:
    """True if `now` falls in any freeze window 'HH:MM-HH:MM' (autonomous actions denied)."""
    now_hm = now.hour * 60 + now.minute
    for w in windows:
        try:
            a, b = w.split("-", 1)
            ah, am = (int(x) for x in a.split(":"))
            bh, bm = (int(x) for x in b.split(":"))
        except (ValueError, AttributeError):
            continue
        if _in_window(now_hm, ah * 60 + am, bh * 60 + bm):
            return True
    return False


def frozen_now() -> bool:
    """Convenience: is an autonomous action frozen right now (UTC) by config?"""
    return is_frozen_now(utcnow(), get_settings().freeze_windows)


def preview_intent(conn: psycopg.Connection, intent_id: str) -> dict[str, Any]:
    """What would this intent change? Uses the tool's preview (else inspect). Read-only."""
    from jarvis.intents.repository import get_intent
    from jarvis.tools.registry import get_tool

    intent = get_intent(conn, intent_id)
    if intent is None:
        raise ValueError(f"unknown intent: {intent_id}")
    tool = get_tool(intent.type)
    if tool is None:
        return {"intent_type": intent.type, "preview": "advisory — no infrastructure change"}
    fn = tool.preview or tool.inspect
    if fn is None:
        return {"intent_type": intent.type, "preview": "no preview available"}
    try:
        return {"intent_type": intent.type, "would_change": fn(intent.target)}
    except Exception as exc:  # noqa: BLE001 — preview is best-effort, never mutates
        return {"intent_type": intent.type, "preview_error": str(exc)}


def pending_approvals(conn: psycopg.Connection) -> int:
    row = conn.execute(
        "SELECT count(*) AS n FROM intents WHERE status = 'proposed'"
    ).fetchone()
    return int(row["n"]) if row else 0


def nudge_if_needed(conn: psycopg.Connection) -> int:
    """Emit a governance.nudge when unapproved proposals exceed the threshold. Returns the count."""
    threshold = get_settings().nudge_pending_threshold
    n = pending_approvals(conn)
    if n >= threshold:
        emit_event(Event(
            type="governance.nudge", severity=Severity.warning, source="governance",
            entity_ref="system:approvals", occurred_at=utcnow(),
            payload={"pending_approvals": n, "threshold": threshold},
            correlation_id=ids.new_id(ids.CORRELATION),
        ))
    return n
