"""State reconciliation — drift detection emits observed/vanished; projector heals/purges."""

from __future__ import annotations

from jarvis.events.models import Event, Severity, utcnow
from jarvis.ingest import reconcile
from jarvis.state.projector import project


class _Ctx:
    def __init__(self, v):
        self.v = v

    def __enter__(self):
        return self.v

    def __exit__(self, *a):
        return False


def test_reconcile_emits_only_divergence(monkeypatch) -> None:
    monkeypatch.setattr(reconcile, "real_containers",
                        lambda ctx: {"web": "running", "db": "running"})

    class _Conn:
        def execute(self, sql, params=None):
            class _R:
                @staticmethod
                def fetchall():
                    return [{"entity": "container:web", "status": "exited"},   # stale → observed
                            {"entity": "container:db", "status": "running"},   # in sync → silent
                            {"entity": "container:ghost_x", "status": "created"}]  # gone → vanished
            return _R()

    monkeypatch.setattr(reconcile.db, "connect", lambda **k: _Ctx(_Conn()))
    emitted: list[Event] = []
    monkeypatch.setattr(reconcile, "emit_event", lambda e: emitted.append(e))
    out = reconcile.reconcile_once()
    assert out == {"observed": 1, "vanished": 1}
    types = sorted(e.type for e in emitted)
    assert types == ["container.observed", "container.vanished"]


def test_reconcile_quiet_when_in_sync(monkeypatch) -> None:
    monkeypatch.setattr(reconcile, "real_containers", lambda ctx: {"web": "running"})

    class _Conn:
        def execute(self, sql, params=None):
            class _R:
                @staticmethod
                def fetchall():
                    return [{"entity": "container:web", "status": "running"}]
            return _R()

    monkeypatch.setattr(reconcile.db, "connect", lambda **k: _Ctx(_Conn()))
    monkeypatch.setattr(reconcile, "emit_event",
                        lambda e: (_ for _ in ()).throw(AssertionError("no event expected")))
    assert reconcile.reconcile_once() == {"observed": 0, "vanished": 0}


class _SpyConn:
    def __init__(self):
        self.sqls: list[str] = []

    def execute(self, sql, params=None):
        self.sqls.append(sql.strip().split()[0].upper())


def _ev(t, entity, **payload):
    return Event(type=t, severity=Severity.info, source="reconcile", entity_ref=entity,
                 occurred_at=utcnow(), payload=payload, correlation_id="corr_x")


def test_projector_observed_updates_and_vanished_deletes() -> None:
    conn = _SpyConn()
    assert project(conn, _ev("container.observed", "container:web", status="running")) is True
    assert conn.sqls[-1] == "INSERT"
    assert project(conn, _ev("container.vanished", "container:ghost_x")) is True
    assert conn.sqls[-1] == "DELETE"
    assert project(conn, _ev("container.destroyed", "container:old")) is True
    assert conn.sqls[-1] == "DELETE"
