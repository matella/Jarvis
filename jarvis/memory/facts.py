"""Durable operator facts — always-on context (city, timezone, preferences).

A fact is a small key→value the agent should recall on EVERY turn, not a semantic memory
retrieved by similarity. Upserted by (scope, key) so updating a fact replaces it. Values are
sanitized on the way in (operator-supplied prose is still untrusted-ish) and rendered into the
conversation context. `scope` is 'global' today; the column leaves room for per-actor facts.
"""

from __future__ import annotations

import psycopg
from pydantic import BaseModel, field_validator

from jarvis.security.sanitize import sanitize

_GLOBAL = "global"
_MAX_KEY = 64
_MAX_VALUE = 500


class UserFact(BaseModel):
    """One durable operator fact at the boundary — validated + versioned."""

    key: str
    value: str
    scope: str = _GLOBAL
    schema_version: int = 1

    @field_validator("key")
    @classmethod
    def _norm_key(cls, v: str) -> str:
        k = v.strip().lower().replace(" ", "_")
        if not k or len(k) > _MAX_KEY:
            raise ValueError(f"fact key must be 1..{_MAX_KEY} chars: {v!r}")
        return k

    @field_validator("value")
    @classmethod
    def _clean_value(cls, v: str) -> str:
        val = sanitize(v.strip())[:_MAX_VALUE]
        if not val:
            raise ValueError("fact value must be non-empty")
        return val


def set_fact(conn: psycopg.Connection, key: str, value: str, *, scope: str = _GLOBAL) -> UserFact:
    """Upsert a fact by (scope, key) — updating replaces the prior value."""
    fact = UserFact(key=key, value=value, scope=scope)
    conn.execute(
        "INSERT INTO user_facts (scope, key, value, schema_version, updated_at) "
        "VALUES (%s, %s, %s, %s, now()) "
        "ON CONFLICT (scope, key) DO UPDATE SET value = EXCLUDED.value, "
        "schema_version = EXCLUDED.schema_version, updated_at = now()",
        (fact.scope, fact.key, fact.value, fact.schema_version),
    )
    return fact


def list_facts(conn: psycopg.Connection, *, scope: str = _GLOBAL) -> list[UserFact]:
    rows = conn.execute(
        "SELECT scope, key, value, schema_version FROM user_facts WHERE scope = %s ORDER BY key",
        (scope,),
    ).fetchall()
    return [UserFact(**r) for r in rows]


def forget_fact(conn: psycopg.Connection, key: str, *, scope: str = _GLOBAL) -> bool:
    """Delete a fact. Returns True if a row was removed."""
    norm = UserFact(key=key, value="_", scope=scope).key  # reuse key normalization
    cur = conn.execute("DELETE FROM user_facts WHERE scope = %s AND key = %s", (scope, norm))
    return cur.rowcount > 0


def facts_block(conn: psycopg.Connection, *, scope: str = _GLOBAL) -> str:
    """Render current facts as a context block (empty string when there are none)."""
    facts = list_facts(conn, scope=scope)
    if not facts:
        return ""
    lines = "\n".join(f"- {f.key}: {f.value}" for f in facts)
    return "What you know about the operator (treat as ground truth):\n" + lines
