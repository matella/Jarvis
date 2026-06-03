"""Module awareness events — correct shape, and best-effort (transport failure never propagates)."""

from __future__ import annotations

import pytest

from jarvis.events.models import Severity
from jarvis.modules import awareness


def test_emit_awareness_builds_entity_verb_event(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list = []
    monkeypatch.setattr(awareness, "emit_event", sent.append)
    ev = awareness.emit_awareness(
        "task.completed", source="tasks", entity_ref="task:1",
        correlation_id="corr_x", title="rent",
    )
    assert sent and sent[0] is ev
    assert ev.type == "task.completed" and ev.source == "tasks"
    assert ev.entity_ref == "task:1" and ev.correlation_id == "corr_x"
    assert ev.severity is Severity.info and ev.payload == {"title": "rent"}


def test_emit_awareness_is_best_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(_ev):
        raise RuntimeError("redis down")

    monkeypatch.setattr(awareness, "emit_event", _boom)
    # A transport failure must NOT propagate — the CRUD write that triggered it already succeeded.
    ev = awareness.emit_awareness("note.created", source="notes", entity_ref="note:1")
    assert ev.type == "note.created"


def test_emit_awareness_generates_correlation_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(awareness, "emit_event", lambda _ev: None)
    ev = awareness.emit_awareness("note.created", source="notes", entity_ref="note:2")
    assert ev.correlation_id.startswith("corr_")
