"""Calendar capability tools — local-event CRUD, graded auto-run. Mirror events are read-only."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from jarvis import db
from jarvis.calendar import repository
from jarvis.calendar.models import CalendarEvent
from jarvis.tools.contract import Rollback, Tool
from jarvis.tools.registry import register


def _opt_str(target: dict[str, Any], key: str) -> str | None:
    v = target.get(key)
    return v if isinstance(v, str) and v.strip() else None


def _require_id(target: dict[str, Any]) -> str:
    event_id = target.get("id")
    if not isinstance(event_id, str) or not event_id:
        raise ValueError("event id is required")
    return event_id


def _parse_dt(target: dict[str, Any], key: str, *, required: bool = False) -> datetime | None:
    raw = _opt_str(target, key)
    if raw is None:
        if required:
            raise ValueError(f"{key} is required (ISO-8601)")
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"invalid {key} (expected ISO-8601): {raw!r}") from exc


def _create_run(target: dict[str, Any], *, timeout_s: int) -> dict[str, Any]:
    title = _opt_str(target, "title")
    if title is None:
        raise ValueError("event title is required")
    event = CalendarEvent(
        title=title,
        starts_at=_parse_dt(target, "starts_at", required=True),
        ends_at=_parse_dt(target, "ends_at"),
        location=str(target.get("location") or ""),
        description=str(target.get("description") or ""),
        all_day=bool(target.get("all_day", False)),
        source_entity_ref=_opt_str(target, "source_entity_ref"),
    )
    with db.connect() as conn:
        repository.create_local(conn, event)
    return {"id": event.id, "entity_ref": event.entity_ref}


def _update_run(target: dict[str, Any], *, timeout_s: int) -> dict[str, Any]:
    event_id = _require_id(target)
    with db.connect() as conn:
        updated = repository.update_local(
            conn, event_id, title=_opt_str(target, "title"),
            starts_at=_parse_dt(target, "starts_at"), ends_at=_parse_dt(target, "ends_at"),
            location=target.get("location") if isinstance(target.get("location"), str) else None,
            description=(target.get("description")
                        if isinstance(target.get("description"), str) else None),
        )
    if updated is None:
        raise ValueError(f"event not found: {event_id}")
    return {"id": event_id}


def _delete_run(target: dict[str, Any], *, timeout_s: int) -> dict[str, Any]:
    event_id = _require_id(target)
    with db.connect() as conn:
        ok = repository.delete_local(conn, event_id)
    if not ok:
        raise ValueError(f"event not found: {event_id}")
    return {"id": event_id, "status": "deleted"}


_PERMS = ["calendar:write"]

register(Tool(
    name="calendar.create_event", version=1, permissions=_PERMS, side_effects=False,
    idempotent=False, max_retries=1, timeout_seconds=5, rollback=Rollback.manual, run=_create_run,
))
register(Tool(
    name="calendar.update_event", version=1, permissions=_PERMS, side_effects=False,
    idempotent=True, max_retries=1, timeout_seconds=5, rollback=Rollback.manual, run=_update_run,
))
register(Tool(
    name="calendar.delete_event", version=1, permissions=_PERMS, side_effects=False,
    idempotent=True, max_retries=1, timeout_seconds=5, rollback=Rollback.manual, run=_delete_run,
))
