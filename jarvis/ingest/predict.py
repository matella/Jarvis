"""Predictive observability — project metric trends toward thresholds, warn before they cross.

Deterministic (least-squares slope over recent `metrics` samples; no LLM — predictions must be
reproducible). Emits `*_trending` signal events, debounced so a sustained trend fires once.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import timedelta

import psycopg

from jarvis import ids
from jarvis.config import get_settings
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import emit_event

# (kind, sample value-key, settings threshold attr, event type)
_SPECS = (
    ("container", "cpu_pct", "cpu_high_pct", "container.cpu_trending"),
    ("container", "mem_pct", "mem_high_pct", "container.memory_trending"),
    ("gpu", "mem_pct", "gpu_mem_high_pct", "gpu.memory_trending"),
)


def _slope_per_min(points: list[tuple[float, float]]) -> float:
    """Least-squares slope of value vs time, expressed per minute."""
    n = len(points)
    if n < 2:
        return 0.0
    mean_t = sum(t for t, _ in points) / n
    mean_v = sum(v for _, v in points) / n
    den = sum((t - mean_t) ** 2 for t, _ in points)
    if den == 0:
        return 0.0
    num = sum((t - mean_t) * (v - mean_v) for t, v in points)
    return (num / den) * 60.0  # per-second → per-minute


def _project(points: list[tuple[float, float]], threshold: float, horizon_min: int) -> float | None:
    """Minutes until the trend crosses `threshold`, if within `horizon_min`; else None."""
    if len(points) < 2:
        return None
    current = points[-1][1]
    if current >= threshold:
        return None  # already over — that's a current alert, not a prediction
    slope = _slope_per_min(points)
    if slope <= 0:
        return None
    eta = (threshold - current) / slope
    return eta if 0 < eta <= horizon_min else None


def _fetch_series(
    conn: psycopg.Connection, since
) -> dict[tuple[str, str], list[tuple[float, dict]]]:
    rows = conn.execute(
        "SELECT entity, kind, sample, ts FROM metrics WHERE ts >= %s ORDER BY ts", (since,)
    ).fetchall()
    series: dict[tuple[str, str], list[tuple[float, dict]]] = {}
    for r in rows:
        series.setdefault((r["entity"], r["kind"]), []).append((r["ts"].timestamp(), r["sample"]))
    return series


@dataclass
class TrendTracker:
    _active: set[tuple[str, str]] = field(default_factory=set)

    def started(self, key: tuple[str, str], trending: bool) -> bool:
        """True only on the transition into a trending state (emit once)."""
        was = key in self._active
        if trending:
            self._active.add(key)
            return not was
        self._active.discard(key)
        return False


def _predict_event(event_type: str, entity: str, payload: dict) -> Event:
    return Event(
        type=event_type, severity=Severity.warning, source="predict", entity_ref=entity,
        occurred_at=utcnow(), payload=payload, correlation_id=ids.new_id(ids.CORRELATION),
    )


def detect_trends(conn: psycopg.Connection, tracker: TrendTracker) -> list[dict]:
    s = get_settings()
    since = utcnow() - timedelta(minutes=s.predict_window_min)
    series = _fetch_series(conn, since)
    thresholds = {
        "cpu_high_pct": s.cpu_high_pct, "mem_high_pct": s.mem_high_pct,
        "gpu_mem_high_pct": s.gpu_mem_high_pct,
    }
    predictions: list[dict] = []
    for (entity, kind), points_raw in series.items():
        if len(points_raw) < s.predict_min_samples:
            continue
        for spec_kind, value_key, thr_attr, event_type in _SPECS:
            if spec_kind != kind:
                continue
            points = [(t, float(sample.get(value_key, 0.0))) for t, sample in points_raw]
            threshold = thresholds[thr_attr]
            eta = _project(points, threshold, s.predict_horizon_min)
            trending = eta is not None
            if tracker.started((entity, event_type), trending):
                payload = {
                    "metric": value_key, "current": round(points[-1][1], 1),
                    "threshold": threshold, "slope_per_min": round(_slope_per_min(points), 3),
                    "eta_minutes": round(eta, 1),
                }
                emit_event(_predict_event(event_type, entity, payload))
                predictions.append({"entity": entity, "type": event_type, **payload})
    return predictions


def run_predictor(*, once: bool = False) -> None:
    from jarvis import db

    tracker = TrendTracker()
    interval = get_settings().predict_interval_s
    while True:
        with db.connect() as conn:
            preds = detect_trends(conn, tracker)
        if preds:
            print(f"[predict] {len(preds)} new trend(s): " + ", ".join(
                f"{p['entity']} {p['type']} eta~{p['eta_minutes']}m" for p in preds
            ), flush=True)
        if once:
            return
        time.sleep(interval)
