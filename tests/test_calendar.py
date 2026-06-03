"""Calendar — model, local-tool parsing/gating, Google parse + sync (mocked). No DB/network."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

import jarvis.calendar.tools  # noqa: F401 — registers calendar.*_event
from jarvis.calendar import google
from jarvis.calendar.models import CalendarEvent, EventSource
from jarvis.tools.registry import get_tool


def test_event_validation_and_window() -> None:
    start = datetime(2026, 6, 2, 9, tzinfo=UTC)
    e = CalendarEvent(title="  Dentist  ", starts_at=start)
    assert e.title == "Dentist" and e.source is EventSource.local and e.is_mirror is False
    assert e.entity_ref == f"calendar:{e.id}"
    with pytest.raises(ValueError):
        CalendarEvent(title="bad", starts_at=start, ends_at=datetime(2026, 6, 2, 8, tzinfo=UTC))


def test_calendar_tools_registered_auto_run() -> None:
    for name in ("calendar.create_event", "calendar.update_event", "calendar.delete_event"):
        assert get_tool(name).side_effects is False


def test_google_to_event_timed_and_all_day() -> None:
    timed = google.to_event({
        "id": "g1", "summary": "Sync", "start": {"dateTime": "2026-06-02T10:00:00+00:00"},
        "end": {"dateTime": "2026-06-02T11:00:00+00:00"}, "status": "confirmed",
    })
    assert timed is not None and timed.source is EventSource.google and timed.external_uid == "g1"
    assert timed.all_day is False

    allday = google.to_event({"id": "g2", "summary": "Trip", "start": {"date": "2026-06-05"}})
    assert allday is not None and allday.all_day is True

    cancelled = {"id": "g3", "start": {"dateTime": "..."}, "status": "cancelled"}
    assert google.to_event(cancelled) is None  # cancelled checked before parsing the bad start
    assert google.to_event({"summary": "no id"}) is None


def test_google_sync_upserts_mirror(monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import contextmanager

    upserted: list[CalendarEvent] = []

    @contextmanager
    def _fake_conn():
        yield object()

    monkeypatch.setattr("jarvis.calendar.repository.upsert_mirror",
                        lambda conn, e: upserted.append(e))
    items = [
        {"id": "g1", "summary": "A", "start": {"dateTime": "2026-06-02T10:00:00+00:00"}},
        {"id": "g2", "summary": "B", "start": {"date": "2026-06-03"}},
        {"summary": "skip — no id"},
    ]
    n = google.sync(fetch_fn=lambda days: items, conn_factory=_fake_conn)
    assert n == 2 and [e.external_uid for e in upserted] == ["g1", "g2"]
