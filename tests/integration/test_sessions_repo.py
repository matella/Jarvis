"""Session repository round-trip — mint/resolve/revoke/expire against a live DB (injected clock)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from jarvis.gateway import sessions

pytestmark = pytest.mark.integration

_T0 = datetime(2026, 6, 2, 12, 0, 0, tzinfo=UTC)


def test_mint_resolve_revoke_expire(db_conn: psycopg.Connection) -> None:
    db_conn.execute("DELETE FROM app_sessions")
    token = sessions.mint_session(db_conn, ttl_days=30, user_agent="pytest", now=lambda: _T0)

    # live within TTL
    assert sessions.resolve_session(db_conn, token, now=lambda: _T0 + timedelta(days=1)) is True
    # last_seen slid forward on resolve
    row = db_conn.execute(
        "SELECT last_seen_at FROM app_sessions WHERE token_hash = %s",
        (sessions.hash_token(token),),
    ).fetchone()
    assert row["last_seen_at"] > _T0

    # expired
    assert sessions.resolve_session(db_conn, token, now=lambda: _T0 + timedelta(days=31)) is False
    # unknown token
    assert sessions.resolve_session(db_conn, "nope", now=lambda: _T0) is False
    # revoked
    sessions.revoke_session(db_conn, token)
    assert sessions.resolve_session(db_conn, token, now=lambda: _T0 + timedelta(days=1)) is False


def test_purge_expired_removes_dead_rows(db_conn: psycopg.Connection) -> None:
    db_conn.execute("DELETE FROM app_sessions")
    live = sessions.mint_session(db_conn, ttl_days=30, now=lambda: _T0)
    dead = sessions.mint_session(db_conn, ttl_days=1, now=lambda: _T0)
    removed = sessions.purge_expired(db_conn, now=lambda: _T0 + timedelta(days=10))
    assert removed == 1
    assert sessions.resolve_session(db_conn, live, now=lambda: _T0 + timedelta(days=10)) is True
    assert sessions.resolve_session(db_conn, dead, now=lambda: _T0 + timedelta(days=10)) is False
