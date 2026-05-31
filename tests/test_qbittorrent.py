"""qBittorrent summary — pure unit (no WebUI)."""

from __future__ import annotations

from jarvis.connectors.qbittorrent import _ETA_INFINITY, summarize


def test_summarize_counts_speed_and_filters_infinite_eta() -> None:
    torrents = [
        {"name": "A", "state": "downloading", "progress": 0.5, "eta": 600, "dlspeed": 1_000_000},
        {"name": "B", "state": "stalledDL", "progress": 0.1, "eta": _ETA_INFINITY, "dlspeed": 0},
        {"name": "C", "state": "queuedDL", "progress": 0.0, "eta": _ETA_INFINITY},
        {"name": "D", "state": "uploading", "progress": 1.0, "eta": 0},
    ]
    s = summarize(torrents, {"dl_info_speed": 1_000_000, "up_info_speed": 50})
    assert s["total"] == 4
    assert s["downloading"] == 2 and s["seeding"] == 1 and s["queued"] == 1
    assert s["dl_speed"] == 1_000_000
    assert s["eta_s"] == 600  # the infinity sentinel is ignored; only A's finite ETA counts
    # items are the active downloads, highest progress first, names sanitized
    assert [i["name"] for i in s["items"]] == ["A", "B"]
    assert s["items"][1]["eta_s"] is None  # B's infinite eta normalized to None


def test_summarize_sanitizes_names() -> None:
    s = summarize([{"name": "ratio email a@b.com", "state": "downloading", "progress": 0.2}], {})
    assert "a@b.com" not in s["items"][0]["name"]  # PII redacted before it hits the spine
