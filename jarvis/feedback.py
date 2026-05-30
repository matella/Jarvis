"""Operator feedback — 👍/👎 on proposals and incidents (the adaptive-attention signal).

Each rating is stored as a queryable row AND emitted as a `feedback.recorded` event, so it lives on
the append-only spine like everything else. `score()` aggregates ratings for a target; later,
adaptive attention can tune notifier/reactor thresholds per entity/type from this plus the
approve/reject/execute + outcome history.
"""

from __future__ import annotations

import psycopg

from jarvis import ids
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import emit_event

VALID_TARGETS = ("intent", "incident", "plan", "routine")


def record(
    conn: psycopg.Connection, *, target_type: str, target_id: str, rating: int,
    actor: str, note: str | None = None,
) -> None:
    """Record a +1/-1 rating; raises ValueError on a bad target or rating."""
    if target_type not in VALID_TARGETS:
        raise ValueError(f"target_type must be one of {VALID_TARGETS}, got {target_type!r}")
    if rating not in (-1, 1):
        raise ValueError("rating must be +1 or -1")
    conn.execute(
        "INSERT INTO feedback (target_type, target_id, rating, note, actor) "
        "VALUES (%s,%s,%s,%s,%s)",
        (target_type, target_id, rating, note, actor),
    )
    emit_event(Event(
        type="feedback.recorded", severity=Severity.info, source="feedback",
        entity_ref=f"{target_type}:{target_id}", occurred_at=utcnow(),
        payload={"target_type": target_type, "target_id": target_id,
                 "rating": rating, "actor": actor},
        correlation_id=ids.new_id(ids.CORRELATION),
    ))


def score(conn: psycopg.Connection, *, target_type: str, target_id: str) -> int:
    """Net score (sum of +1/-1) for a target."""
    row = conn.execute(
        "SELECT coalesce(sum(rating), 0) AS s FROM feedback "
        "WHERE target_type = %s AND target_id = %s",
        (target_type, target_id),
    ).fetchone()
    return int(row["s"]) if row else 0


def list_feedback(conn: psycopg.Connection, limit: int = 30) -> list[dict]:
    return conn.execute(
        "SELECT created_at, actor, target_type, target_id, rating, note "
        "FROM feedback ORDER BY id DESC LIMIT %s",
        (limit,),
    ).fetchall()
