"""Persisted global LLM backend default — `system_state.llm_backend`, mirroring `core/modes.py`.

`get_backend(conn)` is authoritative. `cached_default_backend()` is a short-TTL cached read (its own
connection) for the dispatch hot path, so `scheduler.chat` doesn't hit the DB on every interactive
call. The CLI `jarvis model` writes via `set_backend`; running processes pick it up within the TTL.
"""

from __future__ import annotations

import time

import psycopg

from jarvis.config import get_settings
from jarvis.models.backends.resolve import Backend

_VALID = ("local", "claude")


def get_backend(conn: psycopg.Connection) -> Backend:
    row = conn.execute("SELECT value FROM system_state WHERE key = 'llm_backend'").fetchone()
    if row is not None and row["value"] in _VALID:
        return row["value"]  # type: ignore[return-value]
    return get_settings().llm_default_backend


def set_backend(conn: psycopg.Connection, backend: Backend) -> None:
    if backend not in _VALID:
        raise ValueError(f"invalid backend {backend!r} (expected one of {_VALID})")
    conn.execute(
        "INSERT INTO system_state (key, value, updated_at) VALUES ('llm_backend', %s, now()) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
        (backend,),
    )


_cache: tuple[float, Backend] = (0.0, "local")


def cached_default_backend(*, ttl: float = 10.0) -> Backend:
    """TTL-cached global default for the hot path; degrades to the config default on any error."""
    global _cache
    now = time.monotonic()
    ts, val = _cache
    if now - ts < ttl:
        return val
    from jarvis import db

    try:
        with db.connect() as conn:
            val = get_backend(conn)
    except Exception:  # noqa: BLE001 — DB blip must never break inference; fall back to config
        val = get_settings().llm_default_backend
    _cache = (now, val)
    return val
