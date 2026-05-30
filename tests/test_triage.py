"""Inbox-triage unit tests — noise gate, content framing, one-shot parse. No Redis/model."""

from __future__ import annotations

from jarvis.events.models import Event, Severity, utcnow
from jarvis.notify import triage


def _event(etype: str, **payload) -> Event:
    return Event(
        type=etype, severity=Severity.info, source="x", entity_ref="mail:gmail:1",
        occurred_at=utcnow(), payload=payload, correlation_id="corr_x",
    )


def test_should_push_respects_floor() -> None:
    assert triage.should_push("high", floor="high") is True
    assert triage.should_push("normal", floor="high") is False  # gated out as noise
    assert triage.should_push("normal", floor="normal") is True
    assert triage.should_push("low", floor="low") is True       # floor=low → everything pushes


def test_content_titles_for_mail_and_feed() -> None:
    mail_title, mail_body = triage._content(
        _event("mail.received", account="gmail", **{"from": "boss@x", "subject": "Q3 review",
               "snippet": "let's meet"})
    )
    assert "gmail" in mail_title and "Q3 review" in mail_title
    assert "boss@x" in mail_body and "let's meet" in mail_body

    feed_title, _ = triage._content(_event("feed.item", title="EU AI Act update", summary="..."))
    assert "EU AI Act update" in feed_title


def test_triage_item_parses_and_frames_content_as_untrusted(monkeypatch) -> None:
    seen = {}

    def _fake_chat(role, messages, **k):
        seen["prompt"] = messages[0]["content"]
        return {"message": {"content": '{"importance":"high","summary":"Boss wants a Q3 review."}'}}

    import jarvis.models.scheduler as sched
    monkeypatch.setattr(sched, "chat", _fake_chat)

    importance, summary = triage.triage_item(
        _event("mail.received", account="gmail", subject="Q3", **{"from": "boss@x"})
    )
    assert importance == "high" and "Q3 review" in summary
    # untrusted framing must be present — content is data, never instructions
    assert "untrusted" in seen["prompt"].lower() or "data" in seen["prompt"].lower()


def test_triage_item_degrades_on_bad_json(monkeypatch) -> None:
    import jarvis.models.scheduler as sched
    monkeypatch.setattr(sched, "chat", lambda *a, **k: {"message": {"content": "not json"}})
    importance, summary = triage.triage_item(_event("feed.item", title="x", summary="y"))
    assert importance == "normal" and summary == ""  # safe default, no crash
