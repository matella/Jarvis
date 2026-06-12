"""Unit tests for the post-game brief formatter — no Redis/notify channel."""

from datetime import UTC, datetime

from jarvis.events.models import Event, Severity
from jarvis.notify.hots_brief import format_brief


def _event(players: list[dict], *, winner: int = 0, map_name: str = "Silver City") -> Event:
    return Event(
        type="hots.match_completed",
        severity=Severity.info,
        source="storm-codex",
        occurred_at=datetime.now(UTC),
        correlation_id="corr_test",
        payload={"map": map_name, "mode": 50091, "winner": winner, "players": players},
    )


def _me(win: bool, **kda) -> dict:
    return {"name": "Matella", "hero": "Muradin", "team": 0, "win": win,
            "kda": {"kills": kda.get("k", 0), "deaths": kda.get("d", 0),
                    "takedowns": kda.get("t", 0)}}


def test_victory_brief_from_operator_perspective() -> None:
    ev = _event([_me(True, k=2, d=1, t=18)])
    out = format_brief(ev, "Matella")
    assert out is not None
    title, message, priority = out
    assert "Victoire" in title
    assert message == "Muradin sur Silver City — 2/16/1 · Storm League"  # k/a/d, a = t-k
    assert priority == "default"


def test_defeat_is_high_priority() -> None:
    ev = _event([_me(False, k=5, d=4, t=11)], winner=1)
    out = format_brief(ev, "Matella")
    assert out is not None
    title, message, priority = out
    assert "Défaite" in title
    assert priority == "high"


def test_name_match_is_case_insensitive() -> None:
    ev = _event([_me(True, k=1, d=0, t=9)])
    assert format_brief(ev, "matella") is not None


def test_generic_brief_when_player_unknown() -> None:
    ev = _event([_me(True, k=2, d=1, t=18)], winner=0)
    title, message, _ = format_brief(ev, "")  # no operator name configured
    assert "partie terminée" in title
    assert "équipe bleue" in message


def test_ignores_non_match_events() -> None:
    ev = Event(type="container.started", severity=Severity.info, source="docker",
               occurred_at=datetime.now(UTC), correlation_id="corr_x")
    assert format_brief(ev, "Matella") is None
