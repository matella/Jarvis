"""GPU model telemetry — emit model load/evict events so GPU swap frequency is observable.

Complements the card-level metrics (util/VRAM/temp in `ingest/metrics.py`) with *which* model is
resident: each tick diffs Ollama's resident set against the last and emits `model.loaded` /
`model.evicted` on a change (Hard Rule #7 — "emit model-load events so swap frequency is
observable"). One event per transition, not per sample — steady state is silent. Read-only; a swap
shows up as an `evicted` + a `loaded` close together in the log.
"""

from __future__ import annotations

from jarvis import ids
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import emit_event
from jarvis.models import gpu

# Last resident set seen this process. None until the first sample, so a fresh start seeds the
# baseline without emitting a spurious "loaded" for whatever happened to be warm.
_last: set[str] | None = None


def _emit(event_type: str, model: str) -> None:
    emit_event(Event(
        type=event_type, severity=Severity.info, source="gpu",
        entity_ref=f"model:{model}", occurred_at=utcnow(),
        payload={"model": model}, correlation_id=ids.new_id(ids.CORRELATION),
    ))


def sample_models() -> int:
    """One telemetry tick: diff the resident model set vs last seen, emit a load/evict event per
    change. Returns the number of events emitted (0 when unchanged or Ollama is unreachable)."""
    global _last
    try:
        current = {m["model"] for m in gpu.resident_models()}
    except Exception:  # noqa: BLE001 — Ollama down for this tick → skip, try again next time
        return 0
    if _last is None:
        _last = current  # seed the baseline; don't emit on the very first observation
        return 0
    emitted = 0
    for name in sorted(current - _last):
        _emit("model.loaded", name)
        emitted += 1
    for name in sorted(_last - current):
        _emit("model.evicted", name)
        emitted += 1
    _last = current
    return emitted
