"""Persisted backend-default integration: get/set round-trip + default + validation."""

from __future__ import annotations

import psycopg
import pytest

from jarvis.models.backends.state import get_backend, set_backend

pytestmark = pytest.mark.integration


def test_get_set_backend_round_trip(db_conn: psycopg.Connection) -> None:
    db_conn.execute("DELETE FROM system_state WHERE key = 'llm_backend'")
    assert get_backend(db_conn) == "local"  # default from config when unset
    try:
        set_backend(db_conn, "claude")
        assert get_backend(db_conn) == "claude"
        set_backend(db_conn, "local")
        assert get_backend(db_conn) == "local"
        with pytest.raises(ValueError):
            set_backend(db_conn, "gpt")  # type: ignore[arg-type]
    finally:
        db_conn.execute("DELETE FROM system_state WHERE key = 'llm_backend'")
