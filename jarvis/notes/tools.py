"""Notes capability tools — graded auto-run (no side effects, reversible, on-box)."""

from __future__ import annotations

from typing import Any

from jarvis import db
from jarvis.notes import repository
from jarvis.notes.models import Note
from jarvis.tools.contract import Rollback, Tool
from jarvis.tools.registry import register


def _opt_str(target: dict[str, Any], key: str) -> str | None:
    v = target.get(key)
    return v if isinstance(v, str) and v.strip() else None


def _require_id(target: dict[str, Any]) -> str:
    note_id = target.get("id")
    if not isinstance(note_id, str) or not note_id:
        raise ValueError("note id is required")
    return note_id


def _tags(target: dict[str, Any]) -> list[str] | None:
    raw = target.get("tags")
    if raw is None:
        return None
    if isinstance(raw, str):
        return [t for t in (s.strip() for s in raw.split(",")) if t]
    if isinstance(raw, list):
        return [str(t) for t in raw]
    raise ValueError("tags must be a list or comma-separated string")


def _create_run(target: dict[str, Any], *, timeout_s: int) -> dict[str, Any]:
    note = Note(
        title=_opt_str(target, "title") or "",
        body_md=str(target.get("body_md") or target.get("body") or ""),
        tags=_tags(target) or [],
        source_entity_ref=_opt_str(target, "source_entity_ref"),
    )
    with db.connect() as conn:
        repository.create(conn, note)
    return {"id": note.id, "entity_ref": note.entity_ref, "title": note.title}


def _update_run(target: dict[str, Any], *, timeout_s: int) -> dict[str, Any]:
    note_id = _require_id(target)
    body = target.get("body_md", target.get("body"))
    with db.connect() as conn:
        updated = repository.update(
            conn, note_id,
            title=_opt_str(target, "title"),
            body_md=body if isinstance(body, str) else None,
            pinned=target.get("pinned") if isinstance(target.get("pinned"), bool) else None,
            tags=_tags(target),
        )
    if updated is None:
        raise ValueError(f"note not found: {note_id}")
    return {"id": note_id, "title": updated.title}


def _delete_run(target: dict[str, Any], *, timeout_s: int) -> dict[str, Any]:
    note_id = _require_id(target)
    with db.connect() as conn:
        ok = repository.delete(conn, note_id)
    if not ok:
        raise ValueError(f"note not found: {note_id}")
    return {"id": note_id, "status": "archived"}


_PERMS = ["notes:write"]

register(Tool(
    name="note.create", version=1, permissions=_PERMS, side_effects=False, idempotent=False,
    max_retries=1, timeout_seconds=5, rollback=Rollback.manual, run=_create_run,
))
register(Tool(
    name="note.update", version=1, permissions=_PERMS, side_effects=False, idempotent=True,
    max_retries=1, timeout_seconds=5, rollback=Rollback.manual, run=_update_run,
))
register(Tool(
    name="note.delete", version=1, permissions=_PERMS, side_effects=False, idempotent=True,
    max_retries=1, timeout_seconds=5, rollback=Rollback.manual, run=_delete_run,
))
