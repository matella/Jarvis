"""Notifier unit tests — filtering, formatting, cooldown, log-only channel. No Redis."""

from jarvis.events.models import Event, Severity, utcnow
from jarvis.notify import channel
from jarvis.notify.notifier import NotifierState, _format, should_notify


def _event(etype: str, sev: Severity, **payload) -> Event:
    return Event(
        type=etype, severity=sev, source="x", entity_ref="container:a",
        occurred_at=utcnow(), payload=payload, correlation_id="corr_x",
    )


def test_should_notify_filters() -> None:
    assert should_notify(_event("container.oom_killed", Severity.critical)) is True
    assert should_notify(_event("incident.correlated", Severity.warning, summary="x")) is True
    assert should_notify(_event("container.died", Severity.warning)) is False
    assert should_notify(_event("container.started", Severity.info)) is False


def test_format_incident_vs_critical() -> None:
    title, msg, prio = _format(
        _event("incident.correlated", Severity.warning, summary="3 died", root_cause="oom")
    )
    assert "3 died" in title and msg == "oom" and prio == "high"

    title, _msg, prio = _format(_event("container.oom_killed", Severity.critical))
    assert "CRITICAL" in title and prio == "urgent"


def test_cooldown() -> None:
    state = NotifierState(cooldown_s=300)
    key = ("container.oom_killed", "container:a")
    assert state.allow(key, now=1000.0) is True
    assert state.allow(key, now=1100.0) is False   # within cooldown
    assert state.allow(key, now=1400.0) is True     # cooldown elapsed
    assert state.allow(("other", "container:b"), now=1100.0) is True  # different key


def test_channel_log_only_when_no_url(monkeypatch, capsys) -> None:
    from types import SimpleNamespace

    monkeypatch.setattr(channel, "get_settings", lambda: SimpleNamespace(notify_webhook_url=""))
    assert channel.send(title="t", message="m", priority="default") is False
    assert "[notify:log]" in capsys.readouterr().out
