#!/usr/bin/env python3
"""M0 acceptance check: connect to Postgres (and confirm pgvector) and Redis.

Run from the Mac after `make up` and `make tunnel` are both live, or on the box
itself. Exits 0 only if both services answer; prints which one failed otherwise.
"""

from __future__ import annotations

import sys

import psycopg
import redis

from jarvis.config import get_settings

TIMEOUT_S = 5


def check_postgres(dsn: str) -> str:
    """Verify connectivity and that the pgvector extension is installable."""
    with psycopg.connect(dsn, connect_timeout=TIMEOUT_S, autocommit=True) as conn:
        conn.execute("SELECT 1")
        # The whole reason we run the pgvector image — confirm it loads.
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        (version,) = conn.execute("SHOW server_version").fetchone()  # type: ignore[misc]
    return str(version)


def check_redis(url: str) -> str:
    client = redis.Redis.from_url(url, socket_connect_timeout=TIMEOUT_S)
    client.ping()
    info = client.info("server")
    return str(info["redis_version"])


def main() -> int:
    settings = get_settings()
    ok = True

    try:
        version = check_postgres(settings.postgres_dsn)
        print(f"  postgres   OK  ({settings.postgres_host}:{settings.postgres_port}, v{version}, pgvector ready)")
    except Exception as exc:  # noqa: BLE001 — report any failure, don't swallow it
        ok = False
        print(f"  postgres   FAIL  {settings.postgres_host}:{settings.postgres_port} — {exc}")

    try:
        version = check_redis(settings.redis_url)
        print(f"  redis      OK  ({settings.redis_host}:{settings.redis_port}, v{version})")
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"  redis      FAIL  {settings.redis_host}:{settings.redis_port} — {exc}")

    print("healthcheck: PASS" if ok else "healthcheck: FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
