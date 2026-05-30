"""Presence state — what the orb (6b) shows. Derived from spine state, never free-form.

States: idle | listening | thinking | speaking | alert | frozen. `frozen` (maintenance) and
`alert` (active incidents) are derived from durable state; `listening`/`thinking`/`speaking` are
turn-local and set by the WebSocket handler around a turn. This module gives the durable baseline.
"""

from __future__ import annotations

import psycopg

from jarvis.core.modes import Mode, get_mode

IDLE = "idle"
LISTENING = "listening"
THINKING = "thinking"
SPEAKING = "speaking"
ALERT = "alert"
FROZEN = "frozen"

VALID = {IDLE, LISTENING, THINKING, SPEAKING, ALERT, FROZEN}


_ALERT_WINDOW_MIN = 30


def baseline_presence(conn: psycopg.Connection) -> str:
    """The resting presence from durable state: frozen > alert (recent incident) > idle."""
    if get_mode(conn) is Mode.maintenance:
        return FROZEN
    row = conn.execute(
        "SELECT count(*) AS n FROM incidents "
        "WHERE created_at >= now() - make_interval(mins => %s)",
        (_ALERT_WINDOW_MIN,),
    ).fetchone()
    if row and row["n"]:
        return ALERT
    return IDLE
