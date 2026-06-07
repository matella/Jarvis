"""HotS connector + present routing — egress-guarded fetch (mocked), accurate-failure presenter."""

from __future__ import annotations

import json

from jarvis.agents import conversation as convo
from jarvis.connectors import hots


def _fake_response(payload):
    class _R:
        def read(self):
            return json.dumps(payload).encode()
    return _R()


def test_latest_patches_projects_clean_fields(monkeypatch) -> None:
    payload = {"items": [
        {"patchName": "Hogger Hotfix", "patchType": "Hotfix Patch", "gameVersion": "53.3",
         "liveDate": "2021-03-04T00:00:00", "officialLink": None, "alternateLink": "http://x"},
    ]}
    monkeypatch.setattr(hots, "allowed", lambda host: True)
    monkeypatch.setattr(hots, "guarded_request", lambda url, **k: _fake_response(payload))
    out = hots.latest_patches(5)
    assert out[0] == {"patch": "Hogger Hotfix", "type": "Hotfix Patch", "version": "53.3",
                      "date": "2021-03-04", "link": "http://x"}


def test_reachable_false_on_error(monkeypatch) -> None:
    def boom(url, **k):
        raise OSError("connection refused")
    monkeypatch.setattr(hots, "allowed", lambda host: True)
    monkeypatch.setattr(hots, "guarded_request", boom)
    assert hots.reachable() is False


def test_present_hots_patches_artifact(monkeypatch) -> None:
    monkeypatch.setattr(convo, "_present_hots", convo._present_hots)  # ensure real fn
    monkeypatch.setattr("jarvis.connectors.hots.reachable", lambda: True)
    monkeypatch.setattr("jarvis.connectors.hots.latest_patches",
                        lambda limit=10: [{"patch": "X", "version": "1.0"}])
    out = convo._present_hots("show the latest hots patch")
    assert out.artifacts and out.artifacts[0].title == "HotS Patches"


def test_present_hots_not_reachable(monkeypatch) -> None:
    monkeypatch.setattr("jarvis.connectors.hots.reachable", lambda: False)
    out = convo._present_hots("hots patch")
    assert "isn't connected" in out.message or "reach" in out.message.lower()


def test_present_hots_overlay_matches(monkeypatch) -> None:
    monkeypatch.setattr("jarvis.connectors.hots_overlay.reachable", lambda: True)
    monkeypatch.setattr("jarvis.connectors.hots_overlay.recent_matches",
                        lambda limit=10: [{"map": "Cursed Hollow", "result": "Win"}])
    out = convo._present_hots("show my recent hots matches")
    assert out.artifacts and out.artifacts[0].title == "HotS Matches"


def test_present_hots_overlay_empty(monkeypatch) -> None:
    monkeypatch.setattr("jarvis.connectors.hots_overlay.reachable", lambda: True)
    monkeypatch.setattr("jarvis.connectors.hots_overlay.recent_matches", lambda limit=10: [])
    out = convo._present_hots("hots overlay")
    assert "No HotS matches" in out.message and not out.artifacts


def test_present_hots_patch_still_works(monkeypatch) -> None:
    # A patch query must NOT be hijacked by the overlay branch.
    monkeypatch.setattr("jarvis.connectors.hots.reachable", lambda: True)
    monkeypatch.setattr("jarvis.connectors.hots.latest_patches", lambda limit=10: [{"patch": "X"}])
    out = convo._present_hots("latest hots patch")
    assert out.artifacts[0].title == "HotS Patches"
