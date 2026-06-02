"""Claude backend unit tests — serialize (tool-strip + schema), classify, normalize. No real CLI."""

from __future__ import annotations

import subprocess

import pytest

import jarvis.models.backends.claude as cb


def test_serialize_strips_persona_tool_sections() -> None:
    msgs = [{"role": "system", "content": "You are Jarvis.\n\nWHAT YOU CAN DO:\n- restart"},
            {"role": "user", "content": "hi"}]
    p = cb._serialize_prompt(msgs, fmt=None)
    assert "You are Jarvis." in p and "WHAT YOU CAN DO" not in p and "User: hi" in p


def test_serialize_appends_schema_instruction() -> None:
    p = cb._serialize_prompt([{"role": "user", "content": "q"}], fmt={"type": "object"})
    assert "JSON" in p and "schema" in p.lower()


def test_classify_failures() -> None:
    assert cb._classify(124, "") == "timeout"
    assert cb._classify(1, "Rate limit exceeded") == "resource_exhaustion"
    assert cb._classify(1, "Not logged in") == "permission_denied"
    assert cb._classify(1, "weird") == "unknown"


def test_run_normalizes_stdout(monkeypatch) -> None:
    monkeypatch.setattr(cb.subprocess, "run", lambda *a, **k: type(
        "R", (), {"returncode": 0, "stdout": "Hello there.", "stderr": ""})())
    resp = cb.claude_backend("reasoning", [{"role": "user", "content": "hi"}], fmt=None, timeout=5)
    assert resp["message"]["content"] == "Hello there." and resp["backend_used"] == "claude"


def test_timeout_raises_typed_error(monkeypatch) -> None:
    def _boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=5)
    monkeypatch.setattr(cb.subprocess, "run", _boom)
    with pytest.raises(cb.ClaudeBackendError) as ei:
        cb.claude_backend("reasoning", [{"role": "user", "content": "hi"}], fmt=None, timeout=5)
    assert ei.value.failure_class == "timeout"


def test_nonzero_exit_classifies(monkeypatch) -> None:
    monkeypatch.setattr(cb.subprocess, "run", lambda *a, **k: type(
        "R", (), {"returncode": 1, "stdout": "", "stderr": "rate limit hit"})())
    with pytest.raises(cb.ClaudeBackendError) as ei:
        cb.claude_backend("reasoning", [{"role": "user", "content": "hi"}], fmt=None, timeout=5)
    assert ei.value.failure_class == "resource_exhaustion"
