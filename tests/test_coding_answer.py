"""Wave 1.0 — coding-aware answering: env block, coder routing, _reason dispatch (mocked model)."""

from __future__ import annotations

from jarvis.agents import conversation as convo
from jarvis.agents.conversation import TurnRoute, _Decision
from jarvis.agents.environment import environment_block


def test_environment_block_contains_python_and_stack() -> None:
    block = environment_block()
    assert "Python" in block
    assert "Operator environment" in block
    # at least one known library version line (the suite runs with these installed)
    assert "pydantic" in block


def test_code_answer_uses_coder_role_and_env(monkeypatch) -> None:
    captured: dict = {}

    def fake_chat(role, messages, **kwargs):
        captured["role"] = role
        captured["prompt"] = messages[0]["content"]
        return {"message": {"content": "one-line plan\n```py\nprint('hi')\n```"}}

    monkeypatch.setattr("jarvis.models.scheduler.chat", fake_chat)
    out = convo._code_answer("ctx", "", "How do I read a file in Python?", facts="")
    assert out.route is TurnRoute.answer
    assert captured["role"] == "coder"                      # routed to the coding brain
    assert "Operator environment" in captured["prompt"]     # env grounding injected (#6)
    assert "senior software engineer" in captured["prompt"]  # coding-expert template (#3)
    assert "print('hi')" in out.message


def test_reason_routes_coding_to_code_answer(monkeypatch) -> None:
    # _decide says route=answer, domain=coding → _reason must dispatch to _code_answer.
    monkeypatch.setattr(
        convo, "_decide",
        lambda *a, **k: _Decision(route="answer", message="meh draft", domain="coding"),
    )
    monkeypatch.setattr(
        convo, "assemble_context",
        lambda *a, **k: type("C", (), {"prompt": "", "context_ref": "ctx_x"})(),
    )
    monkeypatch.setattr(convo, "facts_block", lambda conn: "")
    monkeypatch.setattr(convo, "_memory_window", lambda conn, s: "")
    called: dict = {}

    def fake_code_answer(ctx_prompt, memory, utterance, *, facts=""):
        called["hit"] = utterance
        return convo.TurnResult(route=TurnRoute.answer, message="specialist answer")

    monkeypatch.setattr(convo, "_code_answer", fake_code_answer)
    out = convo._reason(conn=None, session=None, utterance="why is my loop off by one?", store=None)
    assert called["hit"] == "why is my loop off by one?"   # coding specialist ran
    assert out.message == "specialist answer"               # not the weak routing draft


def test_reason_general_answer_unchanged(monkeypatch) -> None:
    # domain=general → the routing draft is used directly (one call, no specialist pass).
    monkeypatch.setattr(
        convo, "_decide",
        lambda *a, **k: _Decision(route="answer", message="Canberra.", domain="general"),
    )
    monkeypatch.setattr(
        convo, "assemble_context",
        lambda *a, **k: type("C", (), {"prompt": "", "context_ref": "ctx_x"})(),
    )
    monkeypatch.setattr(convo, "facts_block", lambda conn: "")
    monkeypatch.setattr(convo, "_memory_window", lambda conn, s: "")
    out = convo._reason(conn=None, session=None, utterance="capital of Australia?", store=None)
    assert out.message == "Canberra."


def test_escalation_ladder_retries_on_claude_when_local_empty(monkeypatch) -> None:
    # Local backend + empty answer → one retry pinned to Claude; the escalated answer is used.
    monkeypatch.setattr(convo, "_decide",
                        lambda *a, **k: _Decision(route="answer", message="", domain="general"))
    monkeypatch.setattr(convo, "assemble_context",
                        lambda *a, **k: type("C", (), {"prompt": "", "context_ref": "c"})())
    monkeypatch.setattr(convo, "facts_block", lambda conn: "")
    monkeypatch.setattr(convo, "_memory_window", lambda conn, s: "")
    monkeypatch.setattr("jarvis.models.backends.state.cached_default_backend", lambda: "local")
    seen: list = []

    def fake_plain(ctx, mem, utt, *, facts="", backend=None):
        seen.append(backend)
        return "" if backend is None else "escalated answer"

    monkeypatch.setattr(convo, "_plain_answer", fake_plain)
    out = convo._reason(conn=None, session=None, utterance="explain raft consensus", store=None)
    assert seen == [None, "claude"]              # tried local, then escalated to Claude
    assert out.message == "escalated answer"


def test_no_escalation_when_backend_is_claude(monkeypatch) -> None:
    monkeypatch.setattr("jarvis.models.backends.state.cached_default_backend", lambda: "claude")
    assert convo._should_escalate("") is False   # already on the strong backend → no retry
