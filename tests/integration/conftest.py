"""Integration fixtures — provision a THROWAWAY test DB (via the SSH tunnel) or skip.

The root `tests/conftest.py` points the process at a separate `jarvis_test` database (and
Redis db 15) so the live daemon's real-event traffic in `jarvis` never leaks into a test.
Here we create that DB if absent and migrate it (`alembic upgrade head`) once per session.
If Postgres is unreachable, the whole integration suite skips rather than fails — unit tests
still run anywhere.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
import redis as redis_lib
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from jarvis.config import get_settings
from jarvis.events.stream import get_redis

_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session", autouse=True)
def _provision_test_db() -> None:
    """Create the throwaway test DB (if needed) and migrate it — once, before any test runs.

    Connects to the `postgres` maintenance DB to issue CREATE DATABASE (can't run inside a
    txn, hence autocommit), then shells out to alembic; the subprocess inherits POSTGRES_DB
    from the env the root conftest set, so it migrates the test DB, not the live one.
    """
    settings = get_settings()
    if settings.postgres_db != "jarvis_test":  # safety: never auto-create against the live DB
        return
    admin_dsn = settings.postgres_dsn.rsplit("/", 1)[0] + "/postgres"
    try:
        admin = psycopg.connect(admin_dsn, autocommit=True, connect_timeout=5)
    except psycopg.OperationalError as exc:
        pytest.skip(f"DB unreachable at {settings.postgres_host}:{settings.postgres_port} — {exc}")
    try:
        exists = admin.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (settings.postgres_db,)
        ).fetchone()
        if not exists:
            admin.execute(f'CREATE DATABASE "{settings.postgres_db}"')
    finally:
        admin.close()

    migrate = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if migrate.returncode != 0:
        pytest.skip(f"alembic upgrade head failed on test DB:\n{migrate.stderr}")


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


@pytest.fixture(scope="session")
def redis_client() -> Iterator[redis_lib.Redis]:
    client = get_redis()
    try:
        client.ping()
    except redis_lib.RedisError as exc:
        pytest.skip(f"Redis unreachable — {exc}")
    try:
        yield client
    finally:
        client.close()
