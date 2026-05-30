"""Backlog #3 unit: z-score + anomaly decision + cooldown (pure)."""

from __future__ import annotations

from jarvis.ingest.anomaly import AnomalyState, is_anomaly, zscore


def test_zscore_flags_clear_outlier() -> None:
    history = [10.0] * 30 + [11.0, 9.0, 10.5, 9.5]
    z = zscore(95.0, history)
    assert z is not None and abs(z) > 5  # 95 is wildly out of a ~10 distribution


def test_zscore_none_on_flat_history() -> None:
    assert zscore(10.0, [10.0] * 10) is None  # zero variance → undefined
    assert zscore(10.0, [10.0]) is None  # too small


def test_is_anomaly_respects_min_samples() -> None:
    history = [10.0, 9.0, 11.0]  # only 3 samples
    assert is_anomaly(95.0, history, threshold=3.5, min_samples=20) is False


def test_is_anomaly_true_for_outlier_with_enough_history() -> None:
    history = [10.0 + (i % 3) for i in range(40)]  # varied ~10-12, 40 samples
    assert is_anomaly(99.0, history, threshold=3.5, min_samples=20) is True
    assert is_anomaly(11.0, history, threshold=3.5, min_samples=20) is False  # normal value


def test_anomaly_cooldown_debounces() -> None:
    state = AnomalyState(cooldown_s=300)
    key = ("container:x", "cpu_pct")
    assert state.allow(key, now=1000.0) is True
    assert state.allow(key, now=1100.0) is False  # within cooldown
    assert state.allow(key, now=1400.0) is True  # cooldown elapsed
