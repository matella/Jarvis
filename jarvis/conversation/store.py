"""Session/turn persistence + the in-memory pending-intent state for confirm-to-act.

`conversations`/`messages` are the durable read model and the memory window. The pending-intent
(what the user must confirm to act on) is per-session runtime state held in the gateway's Session
object, not a DB column — it's ephemeral by design and never survives a restart (fail-safe: a
stale "yes" after a crash proposes nothing).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import psycopg
from psycopg.types.json import Json

from jarvis import ids


@dataclass
class Session:
    """Runtime conversation handle: identity + the memory window cursor + pending action."""

    conversation_id: str
    actor: str
    pending_intent_id: str | None = None
    scopes: frozenset[str] = field(default_factory=frozenset)


def start_conversation(conn: psycopg.Connection, *, actor: str) -> Session:
    cid = ids.new_id(ids.CONVERSATION)
    conn.execute(
        "INSERT INTO conversations (id, actor) VALUES (%s, %s)", (cid, actor)
    )
    return Session(conversation_id=cid, actor=actor)


def add_message(
    conn: psycopg.Connection, conversation_id: str, *, role: str, content: str,
    artifacts: dict | None = None,
) -> None:
    conn.execute(
        "INSERT INTO messages (conversation_id, role, content, artifacts) VALUES (%s,%s,%s,%s)",
        (conversation_id, role, content, Json(artifacts or {})),
    )


def recent_messages(
    conn: psycopg.Connection, conversation_id: str, *, limit: int = 10
) -> list[dict]:
    """The memory window — most recent turns, returned oldest-first for prompt assembly."""
    rows = conn.execute(
        "SELECT role, content, ts FROM messages WHERE conversation_id = %s "
        "ORDER BY id DESC LIMIT %s",
        (conversation_id, limit),
    ).fetchall()
    return list(reversed(rows))
