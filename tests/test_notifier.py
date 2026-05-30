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


def _channel_settings(**overrides):
    from types import SimpleNamespace

    base = dict(notify_webhook_url="", ntfy_url="", ntfy_topic="")
    base.update(overrides)
    return SimpleNamespace(**base)


def test_channel_log_only_when_nothing_configured(monkeypatch, capsys) -> None:
    monkeypatch.setattr(channel, "get_settings", lambda: _channel_settings())
    assert channel.send(title="t", message="m", priority="default") is False
    assert "[notify:log]" in capsys.readouterr().out


def test_ntfy_payload_maps_priority_and_tags() -> None:
    p = channel.ntfy_payload(topic="t", title="T", message="M", priority="urgent")
    assert p["topic"] == "t" and p["priority"] == 5 and p["tags"] == ["rotating_light"]

    p = channel.ntfy_payload(topic="t", title="T", message="M", priority="high")
    assert p["priority"] == 4 and p["tags"] == ["warning"]

    # severity wins over a plain priority for the tag (critical → siren)
    p = channel.ntfy_payload(topic="t", title="T", message="M", severity="critical")
    assert p["priority"] == 3 and p["tags"] == ["rotating_light"]

    # ntfy rejects an empty body — we substitute a space
    assert channel.ntfy_payload(topic="t", title="T", message="")["message"] == " "


def test_send_fans_out_to_ntfy_and_webhook(monkeypatch) -> None:
    posts: list[tuple[str, dict]] = []
    monkeypatch.setattr(channel, "get_settings", lambda: _channel_settings(
        ntfy_url="http://ntfy:80", ntfy_topic="home", notify_webhook_url="http://hook",
    ))
    def _capture(url, payload, *, label):
        posts.append((url, payload))
        return True

    monkeypatch.setattr(channel, "_post_json", _capture)

    assert channel.send(title="T", message="M", priority="urgent", severity="critical") is True
    urls = {u for u, _ in posts}
    assert urls == {"http://ntfy:80", "http://hook"}  # both channels fired
    ntfy = next(p for u, p in posts if u == "http://ntfy:80")
    assert ntfy["topic"] == "home" and ntfy["priority"] == 5  # ntfy-shaped payload
