"""Root test config — force the suite onto a THROWAWAY database, never the live one.

The integration suite talks to a real Postgres+Redis (via the SSH tunnel). But the live
`jarvis` daemon is writing real homelab events into that same `jarvis` DB and Redis db 0
the whole time — so a test that reads "recent events" would see the daemon's traffic mixed
in (this caused a flaky correlation/severity failure). We isolate by pointing the test
process at a separate `jarvis_test` database and Redis logical db 15 *before* anything reads
settings, so the live data and the test data never share a namespace.

Override the names with JARVIS_TEST_POSTGRES_DB / JARVIS_TEST_REDIS_DB if needed. Pure
env + cache reset here; the integration conftest provisions (creates + migrates) the DB.
"""

from __future__ import annotations

import os

# Set BEFORE jarvis.config is imported/cached anywhere, so every code path under test —
# app code and fixtures alike — resolves to the throwaway namespace.
os.environ["POSTGRES_DB"] = os.environ.get("JARVIS_TEST_POSTGRES_DB", "jarvis_test")
os.environ["REDIS_DB"] = os.environ.get("JARVIS_TEST_REDIS_DB", "15")

import pytest  # noqa: E402

from jarvis.config import get_settings  # noqa: E402

get_settings.cache_clear()  # drop any settings cached at import time before the override


@pytest.fixture(autouse=True)
def _clear_answer_cache():
    """The coding-answer cache is process-global; reset it around every test for isolation."""
    from jarvis.agents import answer_cache

    answer_cache.clear()
    yield
    answer_cache.clear()
