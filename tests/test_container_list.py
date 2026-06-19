"""Pure tests for the container listing that backs the gateway `/api/containers` endpoint
(consumed by the Aegis operator console). No docker required — `parse_ps` is pure."""
from jarvis.ingest.reconcile import parse_ps


def test_parse_ps_extracts_name_state_status_sorted():
    out = parse_ps(
        '{"Names":"storm-codex","State":"running","Status":"Up 3 days"}\n'
        '{"Names":"old","State":"Exited","Status":"Exited (0) 2 hours ago"}\n'
    )
    assert out == [
        {"name": "old", "state": "exited", "status": "Exited (0) 2 hours ago"},
        {"name": "storm-codex", "state": "running", "status": "Up 3 days"},
    ]


def test_parse_ps_skips_blank_and_malformed_lines():
    assert parse_ps("\n   \n{not json}\n") == []


def test_parse_ps_skips_entries_without_name():
    assert parse_ps('{"State":"running","Status":"Up"}\n') == []
