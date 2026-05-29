"""Summarizer unit tests — assembly + model mocked, no DB/Ollama."""

from contextlib import contextmanager
from datetime import timedelta

import jarvis.agents.summarizer as summ
from jarvis.core.assembly import AssembledContext
from jarvis.events.models import Event, Severity, utcnow


class _FakeStore:
    def __init__(self):
        self.added = []

    def add(self, record):
        self.added.append(record)

    def search(self, embedding, k=5, *, kind=None):
        return []


def _ctx(events) -> AssembledContext:
    return AssembledContext(events=events, memories=[], prompt="PROMPT", context_ref="ctx_test")


def _event(severity: Severity, etype="container.started") -> Event:
    return Event(
        type=etype, severity=severity, source="docker",
        entity_ref="container:x", occurred_at=utcnow(), correlation_id="corr_x",
    )


def test_summarize_filters_notable_and_stores_memory(monkeypatch) -> None:
    events = [_event(Severity.info), _event(Severity.warning, "container.died"),
              _event(Severity.critical, "container.oom_killed")]

    @contextmanager
    def fake_connect(*a, **k):
        yield object()

    monkeypatch.setattr(summ.db, "connect", fake_connect)
    monkeypatch.setattr(summ, "assemble_context", lambda conn, **k: _ctx(events))
    monkeypatch.setattr(
        summ.router, "chat",
        lambda role, messages, **k: {"message": {"content": "  3 containers, 1 OOM.  "}},
    )
    monkeypatch.setattr(summ.router, "embed", lambda text, **k: [0.0] * 8)

    store = _FakeStore()
    result = summ.summarize(timedelta(hours=12), store=store)

    assert result.event_count == 3
    assert result.window == "12h"
    assert result.summary == "3 containers, 1 OOM."  # trimmed
    # only warning+critical are notable
    assert {n.severity for n in result.notable} == {"warning", "critical"}
    # summary stored as episodic memory
    assert len(store.added) == 1
    assert store.added[0].kind == "summary"


def test_summarize_empty_window_skips_model(monkeypatch) -> None:
    @contextmanager
    def fake_connect(*a, **k):
        yield object()

    called = {"chat": False}
    monkeypatch.setattr(summ.db, "connect", fake_connect)
    monkeypatch.setattr(summ, "assemble_context", lambda conn, **k: _ctx([]))

    def _boom(*a, **k):
        called["chat"] = True
        raise AssertionError("model should not be called for an empty window")

    monkeypatch.setattr(summ.router, "chat", _boom)
    result = summ.summarize(timedelta(hours=1), store=_FakeStore())
    assert result.event_count == 0
    assert called["chat"] is False


def test_format_window() -> None:
    assert summ._format_window(timedelta(hours=12)) == "12h"
    assert summ._format_window(timedelta(days=2)) == "2d"
    assert summ._format_window(timedelta(minutes=30)) == "30m"
    assert summ._format_window(timedelta(seconds=45)) == "45s"
