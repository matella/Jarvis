"""6a unit: capability summary, confirmation parsing, intent construction, TurnResult schema."""

from __future__ import annotations

from jarvis.agents import conversation as convo
from jarvis.agents.conversation import (
    TurnResult,
    TurnRoute,
    _Decision,
    _is_affirmative,
    _is_negative,
    _make_intent,
    capability_summary,
)
from jarvis.intents.models import Risk


def test_capability_summary_lists_tools_and_advisory() -> None:
    summary = capability_summary()
    assert "docker.restart_container" in summary
    assert "code.edit_file" in summary
    assert "infra.investigate" in summary  # advisory
    assert "acts on infrastructure" in summary


def test_affirmative_and_negative_parsing() -> None:
    for yes in ("yes", "Yes.", "do it", "go ahead", "confirm", "OK"):
        assert _is_affirmative(yes) is True
    for no in ("no", "Nope", "cancel", "stop", "abort"):
        assert _is_negative(no) is True
    assert _is_affirmative("restart nginx") is False
    assert _is_negative("restart nginx") is False


def test_make_intent_attributes_user_and_requires_approval_for_side_effects() -> None:
    decision = _Decision(
        route="propose", message="restarting", intent_type="docker.restart_container",
        target={"container": "nginx"}, summary="restart nginx", risk=Risk.medium, reversible=True,
        confidence=0.8,
    )
    intent = _make_intent(decision, "ctx_abc", "alice")
    assert intent.type == "docker.restart_container"
    assert intent.requested_by == "user:alice"
    assert intent.target == {"container": "nginx"}
    assert intent.requires_approval is True  # docker.restart_container has side effects
    assert intent.context_ref == "ctx_abc"
    assert intent.reasoning.summary == "restart nginx"


def test_turnresult_serializes() -> None:
    r = TurnResult(route=TurnRoute.answer, message="hi", presence="speaking")
    dumped = r.model_dump(mode="json")
    assert dumped["route"] == "answer"
    assert dumped["message"] == "hi"
    assert dumped["intent_id"] is None
    assert dumped["artifacts"] == [] and dumped["citations"] == []


def test_decide_falls_back_to_answer_on_garbage(monkeypatch) -> None:
    # A non-JSON model reply degrades to a plain answer rather than crashing the turn.
    monkeypatch.setattr(
        convo.router, "chat",
        lambda *a, **k: {"message": {"content": "not json at all"}},
    )
    d = convo._decide("p", correlation_id="corr_x", context_ref="ctx_x")
    assert d.route == "answer"
    assert "not json" in d.message
