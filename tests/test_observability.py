"""Cross-cutting C unit: Prometheus parse → samples, Loki count + spike detection, egress guard."""

from __future__ import annotations

import pytest

from jarvis.ingest.loki import detect_spike, parse_count
from jarvis.ingest.prometheus import parse_instant

PROM = {
    "status": "success",
    "data": {"resultType": "vector", "result": [
        {"metric": {"__name__": "node_memory_Active_bytes", "instance": "host:9100",
                    "job": "node"}, "value": [1700000000, "12345.6"]},
        {"metric": {"__name__": "up", "instance": "host:9100"}, "value": [1700000000, "1"]},
        {"metric": {"instance": "bad"}, "value": [1700000000, "not-a-number"]},  # dropped
    ]},
}

LOKI = {
    "status": "success",
    "data": {"resultType": "vector", "result": [
        {"metric": {"level": "error"}, "value": [1700000000, "42"]},
        {"metric": {"level": "warn"}, "value": [1700000000, "8"]},
    ]},
}


def test_prometheus_parse_to_samples() -> None:
    samples = parse_instant(PROM, "mem")
    assert len(samples) == 2  # the non-numeric value is dropped
    entity, kind, sample = samples[0]
    assert entity == "host:9100" and kind == "prometheus"
    assert sample["value"] == pytest.approx(12345.6)
    assert sample["query"] == "mem"


def test_prometheus_parse_handles_error_status() -> None:
    assert parse_instant({"status": "error"}, "q") == []


def test_loki_parse_count_sums_vector() -> None:
    assert parse_count(LOKI) == 50  # 42 + 8


def test_loki_spike_threshold() -> None:
    assert detect_spike(50, 50) is True
    assert detect_spike(49, 50) is False


def test_observability_egress_guarded(monkeypatch: pytest.MonkeyPatch) -> None:
    # Prometheus/Loki both route fetches through check_url; a non-allowlisted host is blocked before
    # any request. (scrape_once/scan_once catch this per-query and skip, emitting nothing.)
    from jarvis.security import egress

    class S:
        egress_allowlist = ["prometheus.lan"]
    monkeypatch.setattr(egress, "get_settings", lambda: S())
    with pytest.raises(egress.EgressBlocked):
        egress.check_url("http://evil.example:9090/api/v1/query?query=up")
    assert egress.check_url("http://prometheus.lan:9090/api/v1/query?query=up") == "prometheus.lan"
