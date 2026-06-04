"""Active-model override (system_state) + settings REST. No live DB/Ollama (mocked)."""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from jarvis.models.backends import state


def test_get_model_falls_back_to_config(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = type("S", (), {"model_reasoning": "qwen3:4b", "model_coder": "qwen2.5-coder:7b",
                         "model_embedding": "nomic-embed-text"})()
    monkeypatch.setattr(state, "get_settings", lambda: cfg)

    class _Conn:
        def execute(self, *a):
            return type("R", (), {"fetchone": lambda self: None})()
    assert state.get_model(_Conn(), "reasoning") == "qwen3:4b"
    with pytest.raises(ValueError):
        state.get_model(_Conn(), "bogus")


def test_get_model_prefers_override(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Conn:
        def execute(self, *a):
            return type("R", (), {"fetchone": lambda self: {"value": "qwen3:8b"}})()
    assert state.get_model(_Conn(), "reasoning") == "qwen3:8b"


def test_set_model_validates(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list = []

    class _Conn:
        def execute(self, *a):
            calls.append(a)
    state.set_model(_Conn(), "reasoning", "qwen3:8b")
    assert calls and "model_reasoning" in calls[0][1]
    with pytest.raises(ValueError):
        state.set_model(_Conn(), "reasoning", "  ")
    with pytest.raises(ValueError):
        state.set_model(_Conn(), "bogus", "x")


# --- settings REST (TestClient, db + ollama mocked) -------------------------------------------
@contextmanager
def _fake_conn(*_a, **_k):
    class _C:
        def execute(self, *a):
            return type("Cur", (), {"fetchall": lambda self: [], "fetchone": lambda self: None,
                                    "rowcount": 0})()
    yield _C()


def test_set_model_endpoint_validates(monkeypatch: pytest.MonkeyPatch) -> None:
    from starlette.testclient import TestClient

    import jarvis.gateway.app as appmod
    monkeypatch.setattr("jarvis.db.connect", _fake_conn)
    c = TestClient(appmod.app)
    assert c.post("/api/settings/model", json={"role": "bogus", "model": "x"}).status_code == 400
    assert c.post("/api/settings/mode", json={"mode": "nope"}).status_code == 400
    assert c.post("/api/settings/backend", json={"backend": "gpt"}).status_code == 400
