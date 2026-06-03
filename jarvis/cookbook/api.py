"""The cookbook's read API for callers — resolve the backend for an action key.

Callers (research synthesis, document co-write, mail draft, postmortem, …) call `backend_for_action`
to get the operator's chosen backend, then pass it as the `backend=` arg to `scheduler.chat`. This
keeps the router's resolution algorithm + hard overrides untouched — the pref only supplies the
explicit value. Best-effort: any DB problem falls back to the caller's default (never breaks an
inference path).
"""

from __future__ import annotations

import logging

import psycopg

_log = logging.getLogger(__name__)


def backend_for(conn: psycopg.Connection, action_key: str, *, default: str | None = None
                ) -> str | None:
    from jarvis.cookbook import repository

    pref = repository.get_action_pref(conn, action_key)
    return pref.backend if pref is not None else default


def backend_for_action(action_key: str, *, default: str | None = None) -> str | None:
    """Open a connection and resolve the action's backend; fall back to `default` on any error."""
    from jarvis import db

    try:
        with db.connect() as conn:
            return backend_for(conn, action_key, default=default)
    except Exception:  # noqa: BLE001 — a pref lookup must never break the inference it informs
        _log.debug("cookbook backend_for_action(%r) failed; using default", action_key,
                   exc_info=True)
        return default
