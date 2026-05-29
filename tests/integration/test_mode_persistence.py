"""Mode persistence integration: set/get round-trips through system_state."""

from __future__ import annotations

import psycopg
import pytest

from jarvis.core.modes import Mode, get_mode, set_mode

pytestmark = pytest.mark.integration


def test_mode_persists_and_defaults(db_conn: psycopg.Connection) -> None:
    original = get_mode(db_conn)  # default (observe) or whatever's set
    try:
        set_mode(db_conn, Mode.semi_autonomous)
        assert get_mode(db_conn) is Mode.semi_autonomous
        set_mode(db_conn, Mode.maintenance)
        assert get_mode(db_conn) is Mode.maintenance
    finally:
        # restore the row to the original mode (or clear if it was the default)
        set_mode(db_conn, original)
