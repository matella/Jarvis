"""Reminders integration: schedule → due selection → fire (notify) → marked, not re-fired."""

from __future__ import annotations

from datetime import timedelta

import psycopg
import pytest

from jarvis import reminders
from jarvis.events.models import utcnow

pytestmark = pytest.mark.integration


def test_due_selection_and_fire_is_idempotent(db_conn: psycopg.Connection, monkeypatch) -> None:
    pushed: list[str] = []
    monkeypatch.setattr(reminders, "send", lambda **kw: pushed.append(kw["message"]) or True)

    past = reminders.add_reminder(db_conn, "call the dentist", utcnow() - timedelta(minutes=1))
    future = reminders.add_reminder(db_conn, "future thing", utcnow() + timedelta(hours=2))
    try:
        due = {r.id for r in reminders.due_reminders(db_conn)}
        assert past.id in due and future.id not in due  # only past-due is selected

        assert reminders.fire_due(db_conn) == 1          # fires the one due reminder
        assert pushed == ["call the dentist"]            # pushed via the notify channel
        assert reminders.fire_due(db_conn) == 0          # marked fired → never re-fires
    finally:
        db_conn.execute("DELETE FROM reminders WHERE id IN (%s, %s)", (past.id, future.id))
