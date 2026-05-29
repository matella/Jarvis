"""Integration fixtures — connect to the live DB (via the SSH tunnel) or skip.

These tests need Postgres+pgvector reachable at the configured DSN and the schema
migrated (`alembic upgrade head`). If the DB is unreachable, the whole integration
suite skips rather than fails — unit tests still run anywhere.
"""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from jarvis.config import get_settings


@pytest.fixture(scope="session")
def db_conn() -> Iterator[psycopg.Connection]:
    settings = get_settings()
    try:
        conn = psycopg.connect(
            settings.postgres_dsn,
            autocommit=True,
            row_factory=dict_row,
            connect_timeout=5,
        )
    except psycopg.OperationalError as exc:
        pytest.skip(f"DB unreachable at {settings.postgres_host}:{settings.postgres_port} — {exc}")

    # Schema must be migrated; surface a clear skip if not.
    exists = conn.execute("SELECT to_regclass('public.events') IS NOT NULL AS ok").fetchone()
    if not exists or not exists["ok"]:
        conn.close()
        pytest.skip("schema not migrated — run `alembic upgrade head`")

    register_vector(conn)
    try:
        yield conn
    finally:
        conn.close()
