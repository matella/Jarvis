"""Statistical anomaly detection (backlog #3) — flag a metric behaving unusually *for itself*.

Fixed thresholds (P2) and linear trends (P5) miss a metric that's abnormal relative to its OWN
recent distribution. This computes a robust z-score of the latest sample against the rolling history
per entity/metric; a |z| over threshold (with enough history and real variance) emits an
`anomaly.detected` event the correlator can fold in. The math is pure + unit-tested; the scan reads
`metrics` and debounces repeats.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from jarvis import db, ids
from jarvis.config import get_settings
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import emit_event

_METRICS = ("cpu_pct", "mem_pct")


def zscore(value: float, history: list[float]) -> float | None:
    """Robust z-score of `value` vs history (median/MAD). None if history is too flat/small."""
    if len(history) < 2:
        return None
    arr = np.asarray(history, dtype=float)
    median = float(np.median(arr))
    mad = float(np.median(np.abs(arr - median)))
    if mad == 0:
        std = float(np.std(arr))
        if std == 0:
            return None
        return (value - float(np.mean(arr))) / std
    return 0.6745 * (value - median) / mad  # 0.6745 makes MAD a consistent stdev estimator


def is_anomaly(value: float, history: list[float], *, threshold: float, min_samples: int) -> bool:
    if len(history) < min_samples:
        return False
    z = zscore(value, history)
    return z is not None and abs(z) >= threshold


@dataclass
class AnomalyState:
    cooldown_s: int
    _last: dict[tuple[str, str], float] = field(default_factory=dict)

    def allow(self, key: tuple[str, str], now: float) -> bool:
        last = self._last.get(key)
        if last is not None and now - last < self.cooldown_s:
            return False
        self._last[key] = now
        return True


def _series(conn, entity: str, metric: str, limit: int) -> list[float]:
    rows = conn.execute(
        "SELECT (sample->>%s)::float8 AS v FROM metrics WHERE entity = %s "
        "AND sample ? %s ORDER BY ts DESC LIMIT %s",
        (metric, entity, metric, limit),
    ).fetchall()
    return [r["v"] for r in rows if r["v"] is not None]


def scan_once(state: AnomalyState | None = None) -> int:
    """Check each container entity's recent metrics for self-anomalies. Returns count emitted."""
    s = get_settings()
    state = state or AnomalyState(s.anomaly_cooldown_s)
    emitted = 0
    with db.connect() as conn:
        entities = [
            r["entity"] for r in conn.execute(
                "SELECT DISTINCT entity FROM metrics WHERE kind = 'container'"
            ).fetchall()
        ]
        for entity in entities:
            for metric in _METRICS:
                series = _series(conn, entity, metric, s.anomaly_history)
                if not series:
                    continue
                latest, history = series[0], series[1:]
                if not is_anomaly(latest, history, threshold=s.anomaly_z_threshold,
                                  min_samples=s.anomaly_min_samples):
                    continue
                if not state.allow((entity, metric), time.monotonic()):
                    continue
                z = zscore(latest, history)
                emit_event(Event(
                    type="metric.anomaly", severity=Severity.warning, source="anomaly",
                    entity_ref=entity, occurred_at=utcnow(),
                    payload={"metric": metric, "value": round(latest, 1), "z": round(z or 0, 2)},
                    correlation_id=ids.new_id(ids.CORRELATION),
                ))
                emitted += 1
    return emitted


def run_anomaly(*, once: bool = False) -> None:
    state = AnomalyState(get_settings().anomaly_cooldown_s)
    interval = get_settings().anomaly_interval_s
    while True:
        n = scan_once(state)
        if n:
            print(f"[anomaly] flagged {n} metric anomaly(ies)", flush=True)
        if once:
            return
        time.sleep(interval)
