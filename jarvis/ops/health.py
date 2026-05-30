"""Self-observability — Jarvis watches Jarvis.

Worker liveness via Redis heartbeat keys (the supervisor beats each alive thread; a missing key
means a dead/stuck worker), plus DLQ depth, stream pending, recent inference latency, and
dependency reachability. `jarvis self` renders it; a periodic `selfcheck` worker emits a
`jarvis.health` event on degradation (and recovery).
"""

from __future__ import annotations

import threading
import time
import urllib.request

from jarvis import db, ids
from jarvis.config import get_settings
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import emit_event, get_redis


def beat(name: str) -> None:
    """Mark a worker alive (TTL key). Best-effort; never raises."""
    try:
        s = get_settings()
        get_redis().set(f"jarvis:hb:{name}", utcnow().isoformat(), ex=s.heartbeat_ttl_s)
    except Exception:
        pass


def _expected_workers() -> list[str]:
    from jarvis.core.supervisor import workers

    return [name for name, _ in workers(threading.Event())]


def _reachable() -> dict[str, bool]:
    out: dict[str, bool] = {}
    try:
        with db.connect() as c:
            c.execute("SELECT 1")
        out["postgres"] = True
    except Exception:
        out["postgres"] = False
    try:
        get_redis().ping()
        out["redis"] = True
    except Exception:
        out["redis"] = False
    try:
        urllib.request.urlopen(  # noqa: S310 — fixed local URL
            f"{get_settings().ollama_url}/api/version", timeout=5
        ).read()
        out["ollama"] = True
    except Exception:
        out["ollama"] = False
    return out


def _inference_latency() -> dict:
    try:
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT payload->>'duration_ms' AS d FROM events "
                "WHERE type = 'inference.completed' ORDER BY id DESC LIMIT 20"
            ).fetchall()
        vals = [float(r["d"]) for r in rows if r["d"]]
    except Exception:
        vals = []
    return {
        "samples": len(vals),
        "avg_ms": round(sum(vals) / len(vals), 1) if vals else None,
        "last_ms": vals[0] if vals else None,
    }


def health() -> dict:
    s = get_settings()
    r = get_redis()
    reach = _reachable()
    expected = _expected_workers()
    alive = sorted(n for n in expected if r.exists(f"jarvis:hb:{n}"))
    missing = sorted(set(expected) - set(alive))
    try:
        dlq = r.xlen(s.dlq_stream)
    except Exception:
        dlq = None
    try:
        pending = r.xpending(s.events_stream, s.consumer_group)["pending"]
    except Exception:
        pending = None
    degraded = (not all(reach.values())) or bool(missing) or bool(dlq)
    return {
        "reachable": reach,
        "workers": {"expected": expected, "alive": alive, "missing": missing},
        "dlq_depth": dlq,
        "stream_pending": pending,
        "inference": _inference_latency(),
        "degraded": degraded,
    }


def run_selfcheck(*, once: bool = False) -> None:
    interval = get_settings().selfcheck_interval_s
    was_degraded = False
    while True:
        h = health()
        if h["degraded"] and not was_degraded:
            emit_event(_health_event(Severity.warning, h))
            was_degraded = True
        elif not h["degraded"] and was_degraded:
            emit_event(_health_event(Severity.info, h))
            was_degraded = False
        if once:
            return
        time.sleep(interval)


def _health_event(severity: Severity, h: dict) -> Event:
    unreachable = [k for k, v in h["reachable"].items() if not v]
    return Event(
        type="jarvis.health", severity=severity, source="selfcheck", entity_ref="system:jarvis",
        occurred_at=utcnow(),
        payload={
            "degraded": h["degraded"],
            "missing_workers": h["workers"]["missing"],
            "dlq_depth": h["dlq_depth"],
            "unreachable": unreachable,
        },
        correlation_id=ids.new_id(ids.CORRELATION),
    )
