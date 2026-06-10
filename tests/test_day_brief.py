"""Daily-brief composer — assembles modules, best-effort per section. No DB/LLM."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace as NS

import pytest

import jarvis.routines.scheduler as sched


@pytest.fixture
def fixtures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sched, "_briefing_text", lambda conn, hours: "Homelab: all green")
    ev = NS(starts_at=datetime(2026, 6, 2, 9, 0), title="Standup", is_mirror=False,
            source=NS(value="local"))
    monkeypatch.setattr("jarvis.calendar.repository.agenda", lambda conn, s, e: [ev])
    monkeypatch.setattr("jarvis.tasks.repository.due_before",
                        lambda conn, end: [NS(title="Pay rent")])
    monkeypatch.setattr("jarvis.mail.repository.important",
                        lambda conn, limit=5: [NS(subject="Deadline", from_addr="boss@co")])
    monkeypatch.setattr("jarvis.research.repository.recent",
                        lambda conn, limit=3: [NS(query="why is the sky blue",
                                                  status=NS(value="done"))])


def test_day_brief_assembles_all_sections(fixtures: None) -> None:
    text = sched._day_brief_text(object(), 12)
    assert "☀️ Brief du soir" in text
    assert "09:00 Standup" in text
    assert "Pay rent" in text
    assert "Deadline" in text and "boss@co" in text
    assert "why is the sky blue" in text
    assert "Homelab: all green" in text  # homelab health appended last


def test_day_brief_is_best_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    # A failing module section is skipped; the rest of the brief still composes.
    monkeypatch.setattr(sched, "_briefing_text", lambda conn, hours: "Homelab ok")
    monkeypatch.setattr("jarvis.calendar.repository.agenda",
                        lambda conn, s, e: (_ for _ in ()).throw(RuntimeError("no calendar table")))
    monkeypatch.setattr("jarvis.tasks.repository.due_before",
                        lambda conn, end: [NS(title="Ship it")])
    monkeypatch.setattr("jarvis.mail.repository.important", lambda conn, limit=5: [])
    monkeypatch.setattr("jarvis.research.repository.recent", lambda conn, limit=3: [])
    text = sched._day_brief_text(object(), 6)
    assert "Ship it" in text and "Homelab ok" in text
    assert "Aujourd'hui :" not in text  # calendar section raised → skipped, not fatal
