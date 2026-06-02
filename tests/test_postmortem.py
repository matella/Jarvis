"""Postmortem pilot — its inference requests the claude backend (with automatic fallback)."""

from __future__ import annotations

from jarvis.agents import postmortem as pm


def test_decide_requests_claude_backend(monkeypatch) -> None:
    import jarvis.models.scheduler as sched
    seen = {}
    body = '{"what":"x","root_cause":"y","resolution":"z"}'
    monkeypatch.setattr(sched, "chat",
                        lambda *a, **k: seen.update(k) or {"message": {"content": body}})
    out = pm._decide("prompt", "corr_x")
    assert seen.get("backend") == "claude"      # pilot: prefer the stronger model for postmortems
    assert out["root_cause"] == "y"


def test_decide_degrades_on_garbage(monkeypatch) -> None:
    import jarvis.models.scheduler as sched
    monkeypatch.setattr(sched, "chat", lambda *a, **k: {"message": {"content": "not json"}})
    assert pm._decide("prompt", "corr_x") == {}  # malformed → empty fields, never crashes
