"""Code-session persistence — upsert + read accessors."""

from __future__ import annotations

import psycopg
from psycopg.types.json import Json

from jarvis.code.models import CodeSession

_COLS = (
    "id, repo_path, base_ref, worktree_path, task, status, diff_text, files_changed, log_text, "
    "applied, applied_commit, cost_json, schema_version, correlation_id, created_at, completed_at"
)


def _row_to_session(row: dict) -> CodeSession:
    return CodeSession(cost=row.pop("cost_json") or {}, **row)


def save(conn: psycopg.Connection, session: CodeSession) -> CodeSession:
    conn.execute(
        f"INSERT INTO code_sessions ({_COLS}) VALUES "
        "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (id) DO UPDATE SET status=EXCLUDED.status, diff_text=EXCLUDED.diff_text, "
        "files_changed=EXCLUDED.files_changed, log_text=EXCLUDED.log_text, "
        "applied=EXCLUDED.applied, applied_commit=EXCLUDED.applied_commit, "
        "completed_at=EXCLUDED.completed_at",
        (
            session.id, session.repo_path, session.base_ref, session.worktree_path, session.task,
            session.status.value, session.diff_text, session.files_changed, session.log_text,
            session.applied, session.applied_commit, Json(session.cost), session.schema_version,
            session.correlation_id, session.created_at, session.completed_at,
        ),
    )
    return session


def get(conn: psycopg.Connection, session_id: str) -> CodeSession | None:
    row = conn.execute(f"SELECT {_COLS} FROM code_sessions WHERE id = %s", (session_id,)).fetchone()
    return _row_to_session(row) if row else None


def recent(conn: psycopg.Connection, *, limit: int = 20) -> list[CodeSession]:
    rows = conn.execute(
        f"SELECT {_COLS} FROM code_sessions ORDER BY created_at DESC LIMIT %s", (limit,)
    ).fetchall()
    return [_row_to_session(r) for r in rows]
