"""Context-assembly unit tests — fake connection, no DB/Ollama."""

from datetime import timedelta

from jarvis.core.assembly import assemble_context
from jarvis.events.models import Event, Severity, utcnow


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _Conn:
    """Returns the given rows for any query (mimics ORDER BY id DESC: newest first)."""

    def __init__(self, rows):
        self._rows = rows

    def execute(self, sql, params=None):
        return _Cursor(self._rows)


def _events(n: int) -> list[Event]:
    base = utcnow()
    out = []
    for i in range(n):
        out.append(
            Event(
                type="container.started",
                severity=Severity.info,
                source="docker",
                entity_ref=f"container:c{i}",
                occurred_at=base + timedelta(seconds=i),
                correlation_id="corr_x",
            )
        )
    return out


def _rows_newest_first(events: list[Event]) -> list[dict]:
    return [e.model_dump() for e in sorted(events, key=lambda e: e.id, reverse=True)]


def test_assembly_orders_chronologically_within_budget() -> None:
    events = _events(3)
    conn = _Conn(_rows_newest_first(events))
    ctx = assemble_context(conn, since=utcnow() - timedelta(hours=1), query=None)
    assert len(ctx.events) == 3
    # prompt is chronological (oldest first)
    assert [e.id for e in ctx.events] == sorted(e.id for e in events)
    assert ctx.context_ref.startswith("ctx_")
    assert "container.started" in ctx.prompt


def test_assembly_truncates_to_budget() -> None:
    events = _events(5)
    conn = _Conn(_rows_newest_first(events))
    # ~1 token budget → only the newest event fits.
    ctx = assemble_context(conn, since=utcnow() - timedelta(hours=1), query=None, budget_tokens=1)
    assert len(ctx.events) == 1
    newest = max(events, key=lambda e: e.id)
    assert ctx.events[0].id == newest.id


def test_assembly_empty_window() -> None:
    ctx = assemble_context(_Conn([]), since=utcnow(), query=None)
    assert ctx.events == []
    assert "(no events in window)" in ctx.prompt
