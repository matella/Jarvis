"""Mail cache repository — upsert mirror rows + triage + search + inbox accessors.

The cache is a re-syncable mirror (purge + re-sync rebuilds it). Upsert is keyed on (account, uid).
`index=True` embeds from/subject/snippet into the shared search hook so mail is findable + in the
conversation agent's context; tests without an embedder pass `index=False`.
"""

from __future__ import annotations

import psycopg
from psycopg.types.json import Json

from jarvis.mail.models import CachedMessage, Triage
from jarvis.modules import search

_SOURCE = "mail"
_COLS = (
    "id, account, uid, message_id, from_addr, to_addrs, subject, snippet, body_text, "
    "folder, flags, received_at, triage_json, schema_version, synced_at"
)


def _row_to_msg(row: dict) -> CachedMessage:
    triage = row.pop("triage_json")
    return CachedMessage(triage=Triage(**triage) if triage else None, **row)


def upsert(conn: psycopg.Connection, msg: CachedMessage, *, index: bool = True) -> CachedMessage:
    conn.execute(
        f"INSERT INTO mail_cache ({_COLS}) VALUES "
        "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (account, uid) DO UPDATE SET subject=EXCLUDED.subject, "
        "snippet=EXCLUDED.snippet, body_text=EXCLUDED.body_text, flags=EXCLUDED.flags, "
        "triage_json=EXCLUDED.triage_json, synced_at=EXCLUDED.synced_at",
        (
            msg.id, msg.account, msg.uid, msg.message_id, msg.from_addr, msg.to_addrs,
            msg.subject, msg.snippet, msg.body_text, msg.folder, msg.flags, msg.received_at,
            Json(msg.triage.model_dump()) if msg.triage else None, msg.schema_version,
            msg.synced_at,
        ),
    )
    if index:
        search.index_entity(source=_SOURCE, entity_ref=msg.entity_ref,
                            title=msg.subject, text=msg.search_text())
    return msg


def set_triage(conn: psycopg.Connection, msg_id: str, triage: Triage) -> None:
    conn.execute(
        "UPDATE mail_cache SET triage_json = %s WHERE id = %s",
        (Json(triage.model_dump()), msg_id),
    )


def get(conn: psycopg.Connection, msg_id: str) -> CachedMessage | None:
    row = conn.execute(f"SELECT {_COLS} FROM mail_cache WHERE id = %s", (msg_id,)).fetchone()
    return _row_to_msg(row) if row else None


def recent(conn: psycopg.Connection, *, account: str | None = None, limit: int = 50
           ) -> list[CachedMessage]:
    order = "ORDER BY received_at DESC NULLS LAST LIMIT %s"
    if account:
        rows = conn.execute(
            f"SELECT {_COLS} FROM mail_cache WHERE account = %s {order}", (account, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT {_COLS} FROM mail_cache {order}", (limit,)
        ).fetchall()
    return [_row_to_msg(r) for r in rows]


def find(conn: psycopg.Connection, terms: str, *, limit: int = 10) -> list[CachedMessage]:
    """Keyword search across sender/subject/snippet/body, newest first — for 'my mail about X' /
    'last email from Y'. Case-insensitive substring match; empty terms → newest mail."""
    terms = terms.strip()
    if not terms:
        return recent(conn, limit=limit)
    like = f"%{terms}%"
    rows = conn.execute(
        f"SELECT {_COLS} FROM mail_cache WHERE subject ILIKE %s OR from_addr ILIKE %s "
        "OR snippet ILIKE %s OR body_text ILIKE %s ORDER BY received_at DESC NULLS LAST LIMIT %s",
        (like, like, like, like, limit),
    ).fetchall()
    return [_row_to_msg(r) for r in rows]


def important(conn: psycopg.Connection, *, limit: int = 20) -> list[CachedMessage]:
    """High-importance or needs-reply mail — feeds the daily brief."""
    rows = conn.execute(
        f"SELECT {_COLS} FROM mail_cache WHERE triage_json->>'importance' = 'high' "
        "OR (triage_json->>'needs_reply')::boolean = true ORDER BY received_at DESC NULLS LAST "
        "LIMIT %s",
        (limit,),
    ).fetchall()
    return [_row_to_msg(r) for r in rows]


def purge_account(conn: psycopg.Connection, account: str) -> int:
    """Drop an account's mirror (it re-syncs). Returns rows removed."""
    return conn.execute("DELETE FROM mail_cache WHERE account = %s", (account,)).rowcount


def existing_uids(conn: psycopg.Connection, account: str, uids: list[str]) -> set[str]:
    """Of `uids`, which are already cached for the account — so a periodic re-poll can skip them
    (no re-fetch, no re-triage). Empty input → empty set."""
    if not uids:
        return set()
    rows = conn.execute(
        "SELECT uid FROM mail_cache WHERE account = %s AND uid = ANY(%s)", (account, uids)
    ).fetchall()
    return {r["uid"] for r in rows}
