"""Scheduler dispatch fork — local unchanged, claude success/fallback. No Ollama/Claude/DB."""

from __future__ import annotations

import jarvis.models.scheduler as sch


def test_local_path_runs_local(monkeypatch) -> None:
    monkeypatch.setattr(sch, "_resolve_backend", lambda **k: "local")
    seen = {}
    monkeypatch.setattr(sch, "_run_local",
                        lambda *a: seen.setdefault("local", True) or {"message": {"content": "x"}})
    sch.chat("reasoning", [{"role": "user", "content": "hi"}])
    assert seen.get("local") is True


def test_claude_success_passes_through(monkeypatch) -> None:
    monkeypatch.setattr(sch, "_resolve_backend", lambda **k: "claude")
    monkeypatch.setattr("jarvis.models.backends.claude.claude_backend",
                        lambda *a, **k: {"message": {"content": "hello"}, "backend_used": "claude",
                                         "model": "claude"})
    monkeypatch.setattr(sch, "_emit", lambda e: None)
    resp = sch.chat("reasoning", [{"role": "user", "content": "hi"}])  # no schema
    assert resp["backend_used"] == "claude" and resp["message"]["content"] == "hello"


def test_claude_schema_miss_falls_back_to_local(monkeypatch) -> None:
    monkeypatch.setattr(sch, "_resolve_backend", lambda **k: "claude")
    monkeypatch.setattr("jarvis.models.backends.claude.claude_backend",
                        lambda *a, **k: {"message": {"content": "nope"}, "backend_used": "claude"})
    monkeypatch.setattr(sch, "_run_local",
                        lambda *a: {"message": {"content": "{}"}, "backend_used": "local"})
    monkeypatch.setattr(sch, "_notify_fallback", lambda f: None)
    events: list = []
    monkeypatch.setattr(sch, "_emit", events.append)
    resp = sch.chat("reasoning", [{"role": "user", "content": "hi"}],
                    format={"type": "object", "required": ["x"]})
    assert resp["backend_used"] == "local"
    assert any(e.type == "llm.fallback" for e in events)
