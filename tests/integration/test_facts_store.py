"""Durable-fact repository integration: upsert-by-key, list, forget."""

from __future__ import annotations

import psycopg
import pytest

from jarvis.memory.facts import facts_block, forget_fact, list_facts, set_fact

pytestmark = pytest.mark.integration


def test_set_is_upsert_by_key(db_conn: psycopg.Connection) -> None:
    try:
        set_fact(db_conn, "city", "Antwerp")
        set_fact(db_conn, "city", "Brussels")  # same key → replaces, not a second row
        facts = {f.key: f.value for f in list_facts(db_conn)}
        assert facts.get("city") == "Brussels"

        block = facts_block(db_conn)
        assert "city: Brussels" in block and "operator" in block.lower()

        assert forget_fact(db_conn, "City") is True   # key normalization matches on delete
        assert forget_fact(db_conn, "city") is False  # already gone
        assert "city" not in {f.key for f in list_facts(db_conn)}
    finally:
        db_conn.execute("DELETE FROM user_facts WHERE key = 'city'")
