"""Reminders — time-based nudges the operator sets; a worker fires due ones via the notifier.

Self-contained (no external service). Creation is deterministic at the boundary (a Pydantic model
+ validated due time); a small always-on worker polls for due, unfired reminders and pushes them
through the shared notification channel, then marks them fired (kept, not deleted, for audit).
"""

from __future__ import annotations

import time
from datetime import datetime

import psycopg
from pydantic import BaseModel, Field, field_validator

from jarvis import db, ids
from jarvis.config import get_settings
from jarvis.events.models import utcnow
from jarvis.notify.channel import send

_MAX_TEXT = 280


class Reminder(BaseModel):
    """A scheduled nudge at the boundary — validated + versioned."""

    id: str = Field(default_factory=lambda: ids.new_id(ids.REMINDER))
    text: str
    due_at: datetime
    fired: bool = False
    schema_version: int = 1

    @field_validator("text")
    @classmethod
    def _clean(cls, v: str) -> str:
        t = v.strip()[:_MAX_TEXT]
        if not t:
            raise ValueError("reminder text must be non-empty")
        return t


def add_reminder(conn: psycopg.Connection, text: str, due_at: datetime) -> Reminder:
    r = Reminder(text=text, due_at=due_at)
    conn.execute(
        "INSERT INTO reminders (id, text, due_at, fired, schema_version) VALUES (%s,%s,%s,%s,%s)",
        (r.id, r.text, r.due_at, r.fired, r.schema_version),
    )
    return r


def due_reminders(conn: psycopg.Connection, *, now: datetime | None = None) -> list[Reminder]:
    now = now or utcnow()
    rows = conn.execute(
        "SELECT id, text, due_at, fired, schema_version FROM reminders "
        "WHERE fired = false AND due_at <= %s ORDER BY due_at",
        (now,),
    ).fetchall()
    return [Reminder(**r) for r in rows]


def mark_fired(conn: psycopg.Connection, reminder_id: str) -> None:
    conn.execute("UPDATE reminders SET fired = true WHERE id = %s", (reminder_id,))


def list_reminders(conn: psycopg.Connection, *, pending_only: bool = True) -> list[Reminder]:
    sql = "SELECT id, text, due_at, fired, schema_version FROM reminders"
    if pending_only:
        sql += " WHERE fired = false"
    sql += " ORDER BY due_at"
    return [Reminder(**r) for r in conn.execute(sql).fetchall()]


def fire_due(conn: psycopg.Connection) -> int:
    """Push every due, unfired reminder and mark it fired. Returns count fired."""
    fired = 0
    for r in due_reminders(conn):
        send(title="⏰ Reminder", message=r.text, priority="high", reminder_id=r.id)
        mark_fired(conn, r.id)
        fired += 1
    return fired


def run_reminders(*, once: bool = False) -> None:
    interval = get_settings().reminder_check_interval_s
    while True:
        with db.connect(autocommit=True) as conn:
            fire_due(conn)
        if once:
            return
        time.sleep(interval)
