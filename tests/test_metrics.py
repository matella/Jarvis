"""Metrics parsing + threshold-debounce unit tests — no DB/docker/ssh."""

from jarvis.ingest.metrics import (
    ThresholdTracker,
    _evaluate_all,
    _parse_bytes,
    _parse_mem_usage,
    _parse_pct,
)


def test_parse_pct() -> None:
    assert _parse_pct("3.41%") == 3.41
    assert _parse_pct("0.00%") == 0.0
    assert _parse_pct("--") == 0.0
    assert _parse_pct(None) == 0.0


def test_parse_bytes_binary_and_decimal() -> None:
    assert _parse_bytes("4.371MiB") == int(4.371 * 1024**2)
    assert _parse_bytes("30.02GiB") == int(30.02 * 1024**3)
    assert _parse_bytes("958kB") == 958_000
    assert _parse_bytes("128MB") == 128_000_000
    assert _parse_bytes("") == 0


def test_parse_mem_usage() -> None:
    used, limit = _parse_mem_usage("4.371MiB / 30.02GiB")
    assert used == int(4.371 * 1024**2)
    assert limit == int(30.02 * 1024**3)


def test_threshold_tracker_debounces() -> None:
    t = ThresholdTracker()
    hi, lo = "container.cpu_high", "container.cpu_normal"

    def cpu(value: float):
        return t.evaluate("container:x", "cpu", value, 85.0, hi, lo)

    assert cpu(10.0) is None  # below threshold → no event
    high = cpu(95.0)  # cross up → one high event
    assert high is not None and high.type == "container.cpu_high"
    assert high.payload["value"] == 95.0 and high.payload["threshold"] == 85.0
    assert cpu(96.0) is None  # still high → silent (no repeat)
    normal = cpu(20.0)  # recover → one normal event
    assert normal is not None and normal.type == "container.cpu_normal"
    assert cpu(21.0) is None  # still normal → silent


def test_evaluate_all_emits_only_crossings() -> None:
    tracker = ThresholdTracker()
    containers = [
        ("container:busy", "container", {"cpu_pct": 99.0, "mem_pct": 10.0}),
        ("container:idle", "container", {"cpu_pct": 1.0, "mem_pct": 5.0}),
    ]
    gpus = [("gpu:0", "gpu", {"util_pct": 95.0, "mem_pct": 50.0})]
    events = _evaluate_all(tracker, containers, gpus)
    types = sorted(e.type for e in events)
    assert types == ["container.cpu_high", "gpu.utilization_high"]
    # second pass, same readings → no new events (debounced)
    assert _evaluate_all(tracker, containers, gpus) == []
