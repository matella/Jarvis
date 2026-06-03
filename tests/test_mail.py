"""Mail — triage classification + compose draft (one-shot, mocked). No DB/Ollama."""

from __future__ import annotations

import json

import pytest

from jarvis.mail import compose, triage
from jarvis.mail.models import CachedMessage, Importance


def test_cached_message_entity_ref_and_search_text() -> None:
    m = CachedMessage(account="default", uid="42", from_addr="a@b.com", subject="Hi", snippet="yo")
    assert m.entity_ref == f"mail:{m.id}"
    assert "a@b.com" in m.search_text() and "Hi" in m.search_text()


def test_triage_parses_classification() -> None:
    payload = {"category": "work", "importance": "high", "needs_reply": True, "summary": "deadline"}

    def chat(role, messages, **kwargs):
        assert kwargs.get("format") is not None  # grammar-constrained
        return {"message": {"content": json.dumps(payload)}}

    t = triage.classify(from_addr="boss@co", subject="Deadline", body="reply asap", chat_fn=chat)
    assert t.importance is Importance.high and t.needs_reply is True and t.category == "work"


def test_triage_defaults_on_bad_json() -> None:
    t = triage.classify(
        from_addr="x", subject="y", body="z",
        chat_fn=lambda *a, **k: {"message": {"content": "not json"}},
    )
    assert t.importance is Importance.normal and t.needs_reply is False  # neutral default


def test_compose_draft_returns_body() -> None:
    captured: dict = {}

    def chat(role, messages, **kwargs):
        captured["backend"] = kwargs.get("backend")
        return {"message": {"content": "  Sure, see you then.  "}}

    out = compose.draft_reply(
        original_subject="Lunch?", original_body="free friday?",
        instruction="accept warmly", chat_fn=chat, backend="claude",
    )
    assert out == "Sure, see you then." and captured["backend"] == "claude"


def test_compose_rejects_empty_instruction() -> None:
    with pytest.raises(ValueError):
        compose.draft_reply(original_subject="s", original_body="b", instruction="  ",
                            chat_fn=lambda *a, **k: {"message": {"content": "x"}})
