"""Orpheus connector + present routing — reachable/authed states (mocked)."""

from __future__ import annotations

from jarvis.agents import conversation as convo


def test_present_orpheus_not_reachable(monkeypatch) -> None:
    monkeypatch.setattr("jarvis.connectors.orpheus.reachable", lambda: False)
    out = convo._present_orpheus("what's orpheus playing")
    assert "isn't connected" in out.message or "reach" in out.message.lower()


def test_present_orpheus_running_but_dormant(monkeypatch) -> None:
    # Reachable but Spotify not connected → accurate "running, not connected" message, no card.
    monkeypatch.setattr("jarvis.connectors.orpheus.reachable", lambda: True)
    monkeypatch.setattr("jarvis.connectors.orpheus.authed", lambda: False)
    out = convo._present_orpheus("what's orpheus playing")
    assert "Spotify isn't connected" in out.message
    assert not out.artifacts


def test_present_orpheus_now_playing(monkeypatch) -> None:
    monkeypatch.setattr("jarvis.connectors.orpheus.reachable", lambda: True)
    monkeypatch.setattr("jarvis.connectors.orpheus.authed", lambda: True)
    monkeypatch.setattr("jarvis.connectors.orpheus.now_playing",
                        lambda: {"current": {"name": "Song", "artist": "Band"}, "isPlaying": True})
    out = convo._present_orpheus("what's orpheus playing")
    assert out.artifacts and out.artifacts[0].title == "Orpheus — Now Playing"


def test_present_orpheus_idle(monkeypatch) -> None:
    monkeypatch.setattr("jarvis.connectors.orpheus.reachable", lambda: True)
    monkeypatch.setattr("jarvis.connectors.orpheus.authed", lambda: True)
    monkeypatch.setattr("jarvis.connectors.orpheus.now_playing",
                        lambda: {"current": None, "isPlaying": False})
    out = convo._present_orpheus("what's orpheus playing")
    assert "isn't playing" in out.message and not out.artifacts
