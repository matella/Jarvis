"""Tasks capability tools — graded auto-run (no side effects, reversible, on-box).

Reachable only through a validated Intent + the M4 gate (or operator REST). Because `side_effects`
is False and the work is reversible, the conversation agent builds these intents as auto-run; in
`semi_autonomous` mode they execute unattended (Evolution #2). The operator clicking in the UI is
the human gate; here Jarvis proposes and deterministic code executes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from jarvis import db
from jarvis.tasks import repository
from jarvis.tasks.models import Task, TaskPriority, TaskStatus
from jarvis.tools.contract import Rollback, Tool
from jarvis.tools.registry import register


def _opt_str(target: dict[str, Any], key: str) -> str | None:
    v = target.get(key)
    return v if isinstance(v, str) and v.strip() else None


def _parse_due(target: dict[str, Any]) -> datetime | None:
    raw = _opt_str(target, "due_at")
    if raw is None:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"invalid due_at (expected ISO-8601): {raw!r}") from exc


def _require_id(target: dict[str, Any]) -> str:
    task_id = target.get("id")
    if not isinstance(task_id, str) or not task_id:
        raise ValueError("task id is required")
    return task_id


def _enum(value: str | None, enum_cls, label: str):  # type: ignore[no-untyped-def]
    if value is None:
        return None
    try:
        return enum_cls(value)
    except ValueError as exc:
        raise ValueError(f"invalid {label}: {value!r}") from exc


def _create_run(target: dict[str, Any], *, timeout_s: int) -> dict[str, Any]:
    title = _opt_str(target, "title")
    if title is None:
        raise ValueError("task title is required")
    task = Task(
        title=title,
        notes=str(target.get("notes", "")),
        priority=_enum(_opt_str(target, "priority"), TaskPriority, "priority")
        or TaskPriority.normal,
        due_at=_parse_due(target),
        source_entity_ref=_opt_str(target, "source_entity_ref"),
    )
    with db.connect() as conn:
        repository.create(conn, task)
    return {"id": task.id, "entity_ref": task.entity_ref}


def _update_run(target: dict[str, Any], *, timeout_s: int) -> dict[str, Any]:
    task_id = _require_id(target)
    has_due = "due_at" in target
    with db.connect() as conn:
        updated = repository.update(
            conn, task_id,
            title=_opt_str(target, "title"),
            notes=target.get("notes") if isinstance(target.get("notes"), str) else None,
            status=_enum(_opt_str(target, "status"), TaskStatus, "status"),
            priority=_enum(_opt_str(target, "priority"), TaskPriority, "priority"),
            due_at=_parse_due(target),
            set_due=has_due,
        )
    if updated is None:
        raise ValueError(f"task not found: {task_id}")
    return {"id": task_id, "status": updated.status.value}


def _complete_run(target: dict[str, Any], *, timeout_s: int) -> dict[str, Any]:
    task_id = _require_id(target)
    with db.connect() as conn:
        done = repository.complete(conn, task_id)
    if done is None:
        raise ValueError(f"task not found: {task_id}")
    return {"id": task_id, "status": "done"}


def _delete_run(target: dict[str, Any], *, timeout_s: int) -> dict[str, Any]:
    task_id = _require_id(target)
    with db.connect() as conn:
        ok = repository.delete(conn, task_id)
    if not ok:
        raise ValueError(f"task not found: {task_id}")
    return {"id": task_id, "status": "dropped"}


_PERMS = ["tasks:write"]

register(Tool(
    name="task.create", version=1, permissions=_PERMS, side_effects=False, idempotent=False,
    max_retries=1, timeout_seconds=5, rollback=Rollback.manual, run=_create_run,
))
register(Tool(
    name="task.update", version=1, permissions=_PERMS, side_effects=False, idempotent=True,
    max_retries=1, timeout_seconds=5, rollback=Rollback.manual, run=_update_run,
))
register(Tool(
    name="task.complete", version=1, permissions=_PERMS, side_effects=False, idempotent=True,
    max_retries=1, timeout_seconds=5, rollback=Rollback.manual, run=_complete_run,
))
register(Tool(
    name="task.delete", version=1, permissions=_PERMS, side_effects=False, idempotent=True,
    max_retries=1, timeout_seconds=5, rollback=Rollback.manual, run=_delete_run,
))
