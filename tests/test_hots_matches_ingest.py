"""Unit tests for the Storm Codex → spine match-event bridge — no Redis/DB."""

from jarvis.events.models import Severity
from jarvis.ingest.hots_matches import to_event


def _msg(match_id: int = 42) -> dict:
    # shape emitted by storm-codex-server (jarvis.rs match_completed_event)
    return {
        "schema_version": 1,
        "type": "hots.match.completed",
        "correlation_id": "11111111-2222-3333-4444-555555555555",
        "occurred_at": "2026-06-12T21:42:00+00:00",
        "data": {
            "match_id": match_id,
            "map": "Blackheart's Bay",
            "mode": 50091,
            "length": 1294.0,
            "winner": 0,
            "players": [{"hero": "Kael'thas", "team": 0, "win": True}],
        },
    }


def test_translates_match_message_to_spine_event() -> None:
    event = to_event(_msg(2006))
    assert event is not None
    assert event.type == "hots.match_completed"  # entity.verb (single dot) — spine-valid
    assert event.severity is Severity.info
    assert event.source == "storm-codex"
    assert event.entity_ref == "hots-match:2006"
    assert event.correlation_id == "11111111-2222-3333-4444-555555555555"
    assert event.payload["map"] == "Blackheart's Bay"  # apostrophe preserved
    assert event.payload["players"][0]["hero"] == "Kael'thas"


def test_missing_correlation_id_gets_corr_fallback() -> None:
    msg = _msg()
    del msg["correlation_id"]
    event = to_event(msg)
    assert event is not None
    assert event.correlation_id.startswith("corr_")


def test_message_without_match_id_is_ignored() -> None:
    assert to_event({"data": {"map": "Sky Temple"}}) is None
    assert to_event({"foo": "bar"}) is None
