"""Documents capability tools — graded auto-run CRUD (no side effects, reversible, on-box).

AI co-write is NOT a registry tool (its proposal must reach the operator as a diff — the execute
path discards tool output); it lives in `documents.ai.propose_edit`, called by the gateway/UI. The
chat agent creates/updates docs by composing the markdown itself and passing it here.
"""

from __future__ import annotations

from typing import Any

from jarvis import db
from jarvis.documents import repository
from jarvis.documents.models import DocStatus, Document
from jarvis.tools.contract import Rollback, Tool
from jarvis.tools.registry import register


def _opt_str(target: dict[str, Any], key: str) -> str | None:
    v = target.get(key)
    return v if isinstance(v, str) and v.strip() else None


def _require_id(target: dict[str, Any]) -> str:
    doc_id = target.get("id")
    if not isinstance(doc_id, str) or not doc_id:
        raise ValueError("document id is required")
    return doc_id


def _create_run(target: dict[str, Any], *, timeout_s: int) -> dict[str, Any]:
    title = _opt_str(target, "title")
    if title is None:
        raise ValueError("document title is required")
    doc = Document(
        title=title,
        body_md=str(target.get("body_md") or target.get("body") or ""),
        source_entity_ref=_opt_str(target, "source_entity_ref"),
    )
    with db.connect() as conn:
        repository.create(conn, doc, author="jarvis")
    return {"id": doc.id, "entity_ref": doc.entity_ref, "title": doc.title}


def _update_run(target: dict[str, Any], *, timeout_s: int) -> dict[str, Any]:
    doc_id = _require_id(target)
    body = target.get("body_md", target.get("body"))
    status = _opt_str(target, "status")
    with db.connect() as conn:
        updated = repository.update(
            conn, doc_id,
            title=_opt_str(target, "title"),
            body_md=body if isinstance(body, str) else None,
            status=DocStatus(status) if status else None,
            author="jarvis",
        )
    if updated is None:
        raise ValueError(f"document not found: {doc_id}")
    return {"id": doc_id, "status": updated.status.value}


def _delete_run(target: dict[str, Any], *, timeout_s: int) -> dict[str, Any]:
    doc_id = _require_id(target)
    with db.connect() as conn:
        ok = repository.delete(conn, doc_id)
    if not ok:
        raise ValueError(f"document not found: {doc_id}")
    return {"id": doc_id, "status": "archived"}


_PERMS = ["documents:write"]

register(Tool(
    name="document.create", version=1, permissions=_PERMS, side_effects=False, idempotent=False,
    max_retries=1, timeout_seconds=5, rollback=Rollback.manual, run=_create_run,
))
register(Tool(
    name="document.update", version=1, permissions=_PERMS, side_effects=False, idempotent=True,
    max_retries=1, timeout_seconds=5, rollback=Rollback.manual, run=_update_run,
))
register(Tool(
    name="document.delete", version=1, permissions=_PERMS, side_effects=False, idempotent=True,
    max_retries=1, timeout_seconds=5, rollback=Rollback.manual, run=_delete_run,
))
