"""Graceful degradation — when the LLM is down, defer reasoning instead of crashing.

The deterministic spine (ingest → events → projector → notify → state) must keep running even when
inference is unavailable. Reasoning steps that can't run are queued in `deferrals` and replayed by a
drain worker once the model is back. `reasoning_available()` is the gate; `defer`/`drain` are the
queue. This is resilience, not autonomy — deferred work still flows through the same gated path.
"""

from __future__ import annotations

import urllib.request
from collections.abc import Callable
from typing import Any

import psycopg
from psycopg.types.json import Json

from jarvis import ids
from jarvis.config import get_settings
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import emit_event


def reasoning_available() -> bool:
    """Is the inference backend reachable? (the gate for running vs deferring reasoning)."""
    try:
        urllib.request.urlopen(  # noqa: S310 — fixed local URL
            f"{get_settings().ollama_url}/api/version", timeout=3
        ).read()
        return True
    except Exception:
        return False


def defer(conn: psycopg.Connection, kind: str, payload: dict[str, Any]) -> str:
    """Queue a reasoning step for later; emit reasoning.deferred. Returns the deferral id."""
    did = ids.new_id(ids.DEFERRAL)
    conn.execute(
        "INSERT INTO deferrals (id, kind, payload) VALUES (%s, %s, %s)",
        (did, kind, Json(payload)),
    )
    emit_event(Event(
        type="reasoning.deferred", severity=Severity.warning, source="degrade",
        entity_ref=f"deferral:{kind}", occurred_at=utcnow(),
        payload={"kind": kind, **payload}, correlation_id=ids.new_id(ids.CORRELATION),
    ))
    return did


def pending(conn: psycopg.Connection, *, limit: int = 50) -> list[dict]:
    return conn.execute(
        "SELECT id, kind, payload, attempts FROM deferrals ORDER BY created_at LIMIT %s",
        (limit,),
    ).fetchall()


def resolve(conn: psycopg.Connection, deferral_id: str) -> None:
    conn.execute("DELETE FROM deferrals WHERE id = %s", (deferral_id,))


def _bump(conn: psycopg.Connection, deferral_id: str) -> None:
    conn.execute("UPDATE deferrals SET attempts = attempts + 1 WHERE id = %s", (deferral_id,))


def _default_handlers() -> dict[str, Callable[[dict], None]]:
    def _infra_propose(payload: dict) -> None:
        from jarvis.agents.infrastructure import propose_intent

        propose_intent(payload["entity"])

    return {"infra_propose": _infra_propose}


def run_degrade(*, once: bool = False) -> None:
    """Periodically replay deferred reasoning once the LLM is back."""
    import time

    interval = get_settings().verify_interval_s  # reuse a slow-ish cadence
    handlers = _default_handlers()
    while True:
        from jarvis import db

        with db.connect(autocommit=True) as conn:
            n = drain(conn, handlers)
        if n:
            print(f"[degrade] replayed {n} deferred reasoning step(s)", flush=True)
        if once:
            return
        time.sleep(interval)


def drain(conn: psycopg.Connection, handlers: dict[str, Callable[[dict], None]]) -> int:
    """Replay deferred reasoning via per-kind handlers. Count resolved; skips if the LLM is down."""
    if not reasoning_available():
        return 0
    resolved = 0
    for row in pending(conn):
        handler = handlers.get(row["kind"])
        if handler is None:
            continue
        try:
            handler(row["payload"])
            resolve(conn, row["id"])
            resolved += 1
        except Exception as exc:  # noqa: BLE001 — keep draining; a bad one bumps + stays queued
            _bump(conn, row["id"])
            print(f"[degrade] replay {row['id']} failed: {exc!r}", flush=True)
    return resolved
