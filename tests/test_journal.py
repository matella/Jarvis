"""Operational-journal unit tests — FakeConn routes by SQL, no DB."""

from datetime import timedelta

from jarvis.core.journal import build_journal
from jarvis.events.models import utcnow

_NOW = utcnow()


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _Conn:
    """Returns canned rows depending on which table the SQL targets."""

    def execute(self, sql, params=None):
        if "container.deployed" in sql:  # must precede the generic FROM events branch
            return _Cursor([
                {"id": "evt_1", "entity_ref": "container:a", "image": "nginx:1.1",
                 "occurred_at": _NOW - timedelta(minutes=3)},
            ])
        if "FROM events" in sql:
            return _Cursor([
                {"id": "evt_2", "type": "container.died", "severity": "warning",
                 "entity_ref": "container:a", "occurred_at": _NOW - timedelta(minutes=2)},
            ])
        if "FROM incidents" in sql:
            return _Cursor([
                {"incident_id": "inc_1", "severity": "warning", "summary": "a died",
                 "created_at": _NOW - timedelta(minutes=1)},
            ])
        if "FROM intents" in sql:
            return _Cursor([
                {"intent_id": "int_3", "type": "docker.restart_container", "status": "proposed",
                 "risk": "high", "summary": "restart a", "created_at": _NOW},
            ])
        if "FROM executions" in sql:
            return _Cursor([
                {"exec_id": "exec_4", "intent_id": "int_3", "outcome": "failure",
                 "failure_class": "timeout", "created_at": _NOW + timedelta(minutes=1)},
            ])
        return _Cursor([])


def test_journal_merges_and_sorts_chronologically() -> None:
    entries = build_journal(_Conn(), timedelta(hours=1))
    # deploy(-3m) → event(-2m) → incident(-1m) → intent(now) → execution(+1m)
    assert [e.kind for e in entries] == ["deploy", "event", "incident", "intent", "execution"]
    assert [e.ts for e in entries] == sorted(e.ts for e in entries)


def test_journal_severity_normalization() -> None:
    by_kind = {e.kind: e for e in build_journal(_Conn(), timedelta(hours=1))}
    assert by_kind["intent"].severity == "warning"  # risk=high → warning
    assert by_kind["execution"].severity == "warning"  # failure → warning
    assert "timeout" in by_kind["execution"].title
    assert by_kind["event"].severity == "warning"
