"""Context provenance store.

Persists the exact assembled context (prompt + model/params) behind a `context_ref` so
`jarvis explain` can show "why did it decide this" and `jarvis replay` can re-run the model
on the same inputs. Inference itself is non-deterministic and is never re-run to *reproduce*
a decision — only the inputs are recorded (CLAUDE.md replay rule).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import psycopg
from psycopg.types.json import Json
from pydantic import BaseModel, Field

from jarvis.events.models import utcnow


class ContextRecord(BaseModel):
    context_ref: str
    prompt: str
    model: str
    params: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)


def save_context(
    conn: psycopg.Connection,
    *,
    context_ref: str,
    prompt: str,
    model: str,
    params: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        "INSERT INTO contexts (context_ref, prompt, model, params) VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (context_ref) DO NOTHING",
        (context_ref, prompt, model, Json(params or {})),
    )


def get_context(conn: psycopg.Connection, context_ref: str) -> ContextRecord | None:
    row = conn.execute(
        "SELECT * FROM contexts WHERE context_ref = %s", (context_ref,)
    ).fetchone()
    return ContextRecord(**row) if row else None
