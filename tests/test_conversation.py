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


def test_looks_like_remember_triggers_on_explicit_phrasing() -> None:
    assert convo._looks_like_remember("Remember my city is Brussels") is True
    assert convo._looks_like_remember("note that I prefer metric units") is True
    assert convo._looks_like_remember("don't forget the gate code is 1234") is True
    # questions / recall must NOT trigger capture (they go through normal routing)
    assert convo._looks_like_remember("where do I live?") is False
    assert convo._looks_like_remember("do you remember my city?") is False


def test_is_personal_suppresses_search_for_operator_questions() -> None:
    assert convo._is_personal("what city do I live in?") is True
    assert convo._is_personal("where's my car") is True
    # not personal → web search is allowed
    assert convo._is_personal("what's the weather in Paris") is False
    assert convo._is_personal("latest news on the EU AI act") is False


def test_capture_fact_falls_back_to_reason_when_extraction_fails(monkeypatch) -> None:
    monkeypatch.setattr(convo, "_extract_fact", lambda u: None)
    sentinel = TurnResult(route=TurnRoute.answer, message="reasoned")
    monkeypatch.setattr(convo, "_reason", lambda *a, **k: sentinel)
    out = convo._capture_fact(conn=None, session=None, utterance="remember blah", store=None)
    assert out is sentinel  # a misfire degrades to normal reasoning, never a dead end


def test_build_prompt_injects_facts_and_offers_remember_route() -> None:
    prompt = convo._build_prompt(
        "ctx", "", "where do I live?", search_on=False,
        facts="What you know about the operator (treat as ground truth):\n- city: Brussels",
    )
    assert "city: Brussels" in prompt            # facts are in context → recalled
    assert '"remember"' in prompt                # the remember route is offered
    assert "fact_key" in prompt and "fact_value" in prompt


def test_remember_route_stores_fact_and_confirms(monkeypatch) -> None:
    from jarvis.memory.facts import UserFact

    saved: dict[str, str] = {}

    def _fake_set(conn, key, value):
        f = UserFact(key=key, value=value)
        saved[f.key] = f.value
        return f

    monkeypatch.setattr(convo, "set_fact", _fake_set)
    result = convo._remember(conn=None, key="City", value="Brussels")
    assert result.route is TurnRoute.remember
    assert saved == {"city": "Brussels"}
    assert "Brussels" in result.message


def test_remember_handles_invalid_value_without_storing(monkeypatch) -> None:
    def _boom(conn, key, value):
        raise ValueError("fact value must be non-empty")

    monkeypatch.setattr(convo, "set_fact", _boom)
    result = convo._remember(conn=None, key="city", value="")
    assert result.route is TurnRoute.answer and "couldn't note" in result.message


def test_decide_routes_on_active_backend(monkeypatch) -> None:
    # Routing now uses the resolved/active backend (None) so it routes+answers in one call — Claude
    # when it's on (smarter intent), with the router's schema-validate-then-fallback to local.
    import jarvis.models.scheduler as sched
    seen = {}
    monkeypatch.setattr(sched, "chat", lambda *a, **k: seen.update(k)
                        or {"message": {"content": '{"route":"answer","message":"hi"}'}})
    convo._decide("p", correlation_id="corr_x", context_ref="ctx_x")
    assert seen.get("backend") is None  # not pinned local — the active backend routes


def test_present_weather_emits_weather_artifact(monkeypatch) -> None:
    monkeypatch.setattr(convo, "extract_location", lambda t: "Brussels")
    monkeypatch.setattr(convo, "weather_view", lambda loc: {
        "title": "Weather · Brussels", "data": {
            "location": "Brussels", "unit": "°C",
            "current": {"temp": 14, "feels": 12, "code": 3, "label": "Overcast"}, "daily": [],
        }})
    r = convo._present_weather(conn=None, session=None, utterance="weather in Brussels", store=None)
    assert r.route is TurnRoute.answer
    assert r.artifacts and r.artifacts[0].kind == "weather"
    assert "Brussels" in r.message and "14°C" in r.message


def test_present_data_shows_tasks_as_artifact(monkeypatch) -> None:
    from types import SimpleNamespace as NS
    tasks = [NS(title="Pay rent", status=NS(value="open"), priority=NS(value="high"), due_at=None)]
    monkeypatch.setattr("jarvis.tasks.repository.list_open", lambda conn, **k: tasks)
    out = convo._present_data(conn=None, session=None, utterance="show me my tasks", store=None)
    assert out.route is TurnRoute.answer and out.artifacts[0].kind == "auto"
    assert out.artifacts[0].data["value"][0]["title"] == "Pay rent"


def test_present_data_falls_back_when_nothing_matches(monkeypatch) -> None:
    sentinel = TurnResult(route=TurnRoute.answer, message="reasoned")
    monkeypatch.setattr(convo, "_reason", lambda *a, **k: sentinel)
    out = convo._present_data(conn=None, session=None, utterance="show me something weird",
                              store=None)
    assert out is sentinel


def test_looks_like_show() -> None:
    assert convo._looks_like_show("show me my tasks")
    assert convo._looks_like_show("list my inbox")
    assert not convo._looks_like_show("what is the capital of France")


def test_present_weather_no_location_asks_for_city(monkeypatch) -> None:
    monkeypatch.setattr(convo, "extract_location", lambda t: None)
    monkeypatch.setattr(convo, "_operator_city", lambda conn: None)
    out = convo._present_weather(conn=None, session=None, utterance="weather", store=None)
    # No place known → ask (don't fall through to a generic 'no integration' answer).
    assert out.route is TurnRoute.answer and "city" in out.message.lower() and not out.artifacts


def test_present_weather_service_down_says_temporary_not_no_access(monkeypatch) -> None:
    # Rate-limited / down → accurate "try again" message, NOT a misleading "no access" answer.
    def boom(loc):
        raise convo.WeatherUnavailable("429")
    monkeypatch.setattr(convo, "extract_location", lambda t: "Rocourt")
    monkeypatch.setattr(convo, "weather_view", boom)
    out = convo._present_weather(conn=None, session=None, utterance="weather", store=None)
    assert out.route is TurnRoute.answer and not out.artifacts
    assert "Rocourt" in out.message and "no" not in out.message.lower().split()[:3]
    assert "again" in out.message.lower() or "respond" in out.message.lower()


def test_present_weather_place_not_found(monkeypatch) -> None:
    monkeypatch.setattr(convo, "extract_location", lambda t: "Atlantis")
    monkeypatch.setattr(convo, "weather_view", lambda loc: None)  # genuinely unfindable
    out = convo._present_weather(conn=None, session=None, utterance="weather in Atlantis",
                                 store=None)
    assert out.route is TurnRoute.answer and "find" in out.message.lower()


def test_decide_falls_back_to_answer_on_garbage(monkeypatch) -> None:
    # A non-JSON model reply degrades to a plain answer rather than crashing the turn.
    # _decide now goes through the scheduler → router.chat; patch the underlying router call.
    from jarvis.models import router

    monkeypatch.setattr(
        router, "chat",
        lambda *a, **k: {"message": {"content": "not json at all"}},
    )
    d = convo._decide("p", correlation_id="corr_x", context_ref="ctx_x")
    assert d.route == "answer"
    assert "not json" in d.message
