"""Connectors batch — Pi-hole / Sonarr+Radarr / Actual / GitHub presenters + routing."""

from __future__ import annotations

from jarvis.agents import conversation as convo
from jarvis.connectors import arr, pihole


def test_routing_new_targets() -> None:
    assert convo.fastpath_route("how is the pihole doing?") == "present:pihole"
    assert convo.fastpath_route("what's sonarr downloading?") == "present:arr"
    assert convo.fastpath_route("how is my budget this month?") == "present:budget"
    assert convo.fastpath_route("any open pull requests on github?") == "present:github"


def test_present_pihole_summary(monkeypatch) -> None:
    monkeypatch.setattr("jarvis.connectors.pihole.reachable", lambda: True)
    monkeypatch.setattr("jarvis.connectors.pihole.summary", lambda: {
        "queries_today": 1000, "blocked_today": 150, "percent_blocked": 15.0,
        "active_clients": 7, "domains_on_blocklist": 120000})
    out = convo._present_pihole("pihole stats")
    assert "1000" in out.message and "15.0%" in out.message and out.artifacts


def test_present_pihole_not_connected(monkeypatch) -> None:
    monkeypatch.setattr("jarvis.connectors.pihole.reachable", lambda: False)
    out = convo._present_pihole("dns stats")
    assert "isn't connected" in out.message or "PIHOLE_PASSWORD" in out.message


def test_present_arr_combined(monkeypatch) -> None:
    monkeypatch.setattr("jarvis.connectors.arr.reachable", lambda app: True)
    monkeypatch.setattr("jarvis.connectors.arr.queue",
                        lambda app, limit=10: [{"title": "X", "status": "downloading",
                                                "time_left": "01:00", "done_pct": 50.0}])
    monkeypatch.setattr("jarvis.connectors.arr.upcoming", lambda app, days=7, limit=12: [])
    out = convo._present_arr("what's sonarr downloading")
    assert "1 download" in out.message and out.artifacts


def test_present_budget_dormant(monkeypatch) -> None:
    monkeypatch.setattr("jarvis.connectors.actualbudget.reachable", lambda: True)
    monkeypatch.setattr("jarvis.connectors.actualbudget.authed", lambda: False)
    out = convo._present_budget("how's my budget")
    assert "ACTUAL_PASSWORD" in out.message


def test_present_github_unconfigured(monkeypatch) -> None:
    monkeypatch.setattr("jarvis.connectors.github.configured", lambda: False)
    out = convo._present_github("github prs")
    assert "isn't connected" in out.message or "GITHUB_PAT" in out.message


def test_present_github_error_reported(monkeypatch) -> None:
    monkeypatch.setattr("jarvis.connectors.github.configured", lambda: True)
    monkeypatch.setattr("jarvis.connectors.github.my_open_prs", lambda: {"error": "boom"})
    out = convo._present_github("github pull requests")
    assert "failed" in out.message and "boom" in out.message


def test_pihole_summary_parses_v6(monkeypatch) -> None:
    monkeypatch.setattr(pihole, "_auth", lambda: "sid123")
    monkeypatch.setattr(pihole, "_logout", lambda sid: None)

    class _Resp:
        @staticmethod
        def read():
            return (b'{"queries": {"total": 50, "blocked": 5, "percent_blocked": 10.0},'
                    b' "clients": {"active": 3}, "gravity": {"domains_being_blocked": 99}}')

    monkeypatch.setattr(pihole, "guarded_request", lambda *a, **k: _Resp())
    s = pihole.summary()
    assert s["queries_today"] == 50 and s["percent_blocked"] == 10.0


def test_arr_queue_computes_done_pct(monkeypatch) -> None:
    monkeypatch.setattr(arr, "_get", lambda app, path, **k: {
        "records": [{"title": "Ep", "status": "downloading", "timeleft": "00:10",
                     "size": 100.0, "sizeleft": 25.0}]})
    q = arr.queue("sonarr")
    assert q[0]["done_pct"] == 75.0


def test_restart_fastpath_proposes_intent(monkeypatch) -> None:
    # Deterministic restart: target validated against state, Intent filed, confirmation armed.
    class _Conn:
        def execute(self, sql, params=None):
            class _R:
                @staticmethod
                def fetchall():
                    return [{"entity": "container:it-tools"}, {"entity": "container:pihole"}]
            return _R()

    saved = {}
    monkeypatch.setattr(convo, "insert_intent", lambda conn, i: saved.update(intent=i))

    class _S:
        actor = "test"
        pending_intent_id = None

    s = _S()
    out = convo._propose_restart(_Conn(), s, "redémarre le conteneur it-tools")
    assert out.route.value == "propose" and "it-tools" in out.message
    assert s.pending_intent_id == saved["intent"].intent_id
    assert saved["intent"].type == "docker.restart_container"
    assert saved["intent"].target == {"container": "it-tools"}


def test_restart_fastpath_unknown_target(monkeypatch) -> None:
    class _Conn:
        def execute(self, sql, params=None):
            class _R:
                @staticmethod
                def fetchall():
                    return [{"entity": "container:pihole"}]
            return _R()

    class _S:
        actor = "test"
        pending_intent_id = None

    out = convo._propose_restart(_Conn(), _S(), "restart the foobar container")
    assert out.route.value == "answer" and "didn't recognise" in out.message


def test_restart_routing() -> None:
    assert convo.fastpath_route("redémarre le conteneur it-tools") == "restart"
    assert convo.fastpath_route("restart pihole please") == "restart"
    # "when did the server restart?" also routes here — acceptable (it asks, no action)
    assert convo.fastpath_route("when did the server restart?") == "restart"
