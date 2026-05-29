# Phase 5 — Predictive Observability (design spec)

> Date: 2026-05-29 · Phase 5 (ambient). Project resource metrics toward their thresholds and
> warn BEFORE they cross — "container X will hit its memory limit in ~20m". Deterministic trend
> math over the `metrics` table (no LLM — predictions must be reproducible).

## Decision
A deterministic trend analyzer emits `*_trending` predictive signal events; they flow to the
notifier + journal. The reactor still acts only on real failures (per the chosen scope).

## Components
- **`ingest/predict.py`**:
  - `_slope_per_min(points)` — least-squares slope of value over time (per minute), pure.
  - `_project(points, threshold, horizon_min)` — current = last value; if already ≥ threshold →
    None (that's a current alert, not a prediction); if slope ≤ 0 → None; else
    eta = (threshold − current)/slope; return eta if 0 < eta ≤ horizon else None.
  - `_fetch_series(conn, since)` — recent metrics rows grouped by (entity, kind).
  - `TrendTracker` — emit once when a trend starts, clear silently when it stops (debounce).
  - `detect_trends(tracker)` — per entity+metric spec, project; on a NEW trend emit a predictive
    event and return the prediction. `run_predictor(once)` loops it (holds the tracker).
  - specs: container cpu_pct/mem_pct + gpu mem_pct, vs the existing high thresholds.
- **predictive event types**: `container.cpu_trending`, `container.memory_trending`,
  `gpu.memory_trending` (severity warning, source `predict`; payload current/threshold/slope/eta).
- **notifier**: `should_notify` also fires on `*_trending` (so predictions page the operator).
- **supervisor**: add `predict` worker (holds its own TrendTracker).
- **config**: `predict_interval_s=60`, `predict_window_min=30`, `predict_horizon_min=30`,
  `predict_min_samples=5`.
- **CLI**: `jarvis predict [--once]` (run a cycle, print predictions).

## Testing → acceptance
- **Unit**: `_slope_per_min` (rising>0 / flat=0 / falling<0); `_project` (rising→eta, flat→None,
  already-over→None, falling→None); `TrendTracker` start/stop debounce; `should_notify` on
  `_trending`.
- **Integration** (DB): seed rising mem_pct samples for a fake entity → `detect_trends` returns
  one prediction; flat samples → none.
- **Live**: seed climbing mem_pct samples → `jarvis predict` reports "memory_trending, eta ~Nm";
  it appears in `jarvis journal`. Cleaned up.

## Process note
Lightweight path (saved preference): this spec is the record; subagent review loop + separate
writing-plans pass skipped. Implementation proceeds directly.
