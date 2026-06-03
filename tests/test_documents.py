"""Documents — model, tools, and AI co-write proposal. No DB/Ollama (round-trip = integration)."""

from __future__ import annotations

import pytest

from jarvis.documents import ai, tools
from jarvis.documents.models import DocStatus, Document
from jarvis.tools.registry import get_tool


def test_document_validation() -> None:
    d = Document(title="  Plan  ", body_md="# Plan")
    assert d.title == "Plan" and d.status is DocStatus.draft
    assert d.entity_ref == f"document:{d.id}"
    with pytest.raises(ValueError):
        Document(title="  ")


def test_document_tools_registered_auto_run() -> None:
    for name in ("document.create", "document.update", "document.delete"):
        tool = get_tool(name)
        assert tool is not None and tool.side_effects is False


def test_create_run_requires_title() -> None:
    with pytest.raises(ValueError):
        tools._create_run({"body": "x"}, timeout_s=5)


def test_create_run_builds_document(monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import contextmanager

    saved: list[Document] = []

    @contextmanager
    def _fake_conn():
        yield object()

    monkeypatch.setattr(tools.db, "connect", _fake_conn)
    monkeypatch.setattr(tools.repository, "create", lambda conn, doc, **k: saved.append(doc))
    out = tools._create_run({"title": "Essay", "body": "# Essay\nbody"}, timeout_s=5)
    assert saved[0].title == "Essay" and "body" in saved[0].body_md
    assert out["entity_ref"].startswith("document:")


def test_propose_edit_is_one_shot_and_returns_proposal(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def _fake_chat(role, messages, **kwargs):
        captured["messages"] = messages
        captured["backend"] = kwargs.get("backend")
        return {"message": {"content": "  rewritten markdown  "}}

    monkeypatch.setattr(ai.scheduler, "chat", _fake_chat)
    out = ai.propose_edit(body_md="old text", instruction="make it punchy", backend="claude")
    assert out == "rewritten markdown"  # trimmed; the table is NOT written here
    assert "make it punchy" in captured["messages"][1]["content"]
    assert "old text" in captured["messages"][1]["content"]
    assert captured["backend"] == "claude"


def test_propose_edit_rejects_empty_instruction() -> None:
    with pytest.raises(ValueError):
        ai.propose_edit(body_md="x", instruction="   ")
