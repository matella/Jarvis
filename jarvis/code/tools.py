"""Code capability tools — start_session + apply_patch are GATED; discard is auto-run.

`code.start_session` spawns a coding process (compute/egress) and `code.apply_patch` writes a real
repo — both `side_effects=True` → the agent gates them (human confirms; mode ladder governs).
`code.discard_session` (reversible cleanup) is auto-run. The only path to a live repo is the gated
apply; OpenCode itself only ever touches the throwaway worktree.
"""

from __future__ import annotations

from typing import Any

from jarvis import db
from jarvis.code import repository
from jarvis.code.harness import GitOps, run_session
from jarvis.code.models import CodeStatus
from jarvis.events.models import utcnow
from jarvis.modules.awareness import emit_awareness
from jarvis.tools.contract import Rollback, Tool
from jarvis.tools.registry import register


def _require(target: dict[str, Any], key: str) -> str:
    v = target.get(key)
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f"{key} is required")
    return v.strip()


def _start_run(target: dict[str, Any], *, timeout_s: int) -> dict[str, Any]:
    repo_path = _require(target, "repo_path")
    task = _require(target, "task")
    base_ref = target.get("base_ref") if isinstance(target.get("base_ref"), str) else "HEAD"
    session = run_session(repo_path, task, base_ref=base_ref or "HEAD")
    with db.connect() as conn:
        repository.save(conn, session)
    emit_awareness(
        "code.session_ready" if session.status is CodeStatus.ready else "code.session_failed",
        source="code", entity_ref=session.entity_ref, correlation_id=session.correlation_id,
        status=session.status.value, files_changed=len(session.files_changed),
    )
    return {"session_id": session.id, "status": session.status.value,
            "files_changed": session.files_changed}


def _apply_run(target: dict[str, Any], *, timeout_s: int) -> dict[str, Any]:
    session_id = _require(target, "session_id")
    with db.connect() as conn:
        session = repository.get(conn, session_id)
        if session is None:
            raise ValueError(f"code session not found: {session_id}")
        if session.status is not CodeStatus.ready or not session.diff_text:
            raise ValueError(f"session {session_id} has no reviewable diff to apply")
        commit = GitOps().apply_patch(
            session.repo_path, session.diff_text, message=f"jarvis code session {session.id}: "
            f"{session.task[:60]}",
        )
        applied = session.model_copy(update={
            "applied": True, "applied_commit": commit, "status": CodeStatus.applied,
            "completed_at": utcnow(),
        })
        repository.save(conn, applied)
    emit_awareness("code.patch_applied", source="code", entity_ref=session.entity_ref,
                   correlation_id=session.correlation_id, commit=commit)
    return {"session_id": session_id, "applied_commit": commit}


def _discard_run(target: dict[str, Any], *, timeout_s: int) -> dict[str, Any]:
    session_id = _require(target, "session_id")
    with db.connect() as conn:
        session = repository.get(conn, session_id)
        if session is None:
            raise ValueError(f"code session not found: {session_id}")
        if session.worktree_path:
            GitOps().remove_worktree(session.repo_path, session.worktree_path)
        repository.save(conn, session.model_copy(update={"status": CodeStatus.discarded}))
    return {"session_id": session_id, "status": "discarded"}


register(Tool(
    name="code.start_session", version=1, permissions=["code:run"],
    side_effects=True,  # spawns a coding process → gated
    idempotent=False, max_retries=0, timeout_seconds=900, rollback=Rollback.manual, run=_start_run,
))
register(Tool(
    name="code.apply_patch", version=1, permissions=["code:write"],
    side_effects=True,  # writes a real repo → gated
    idempotent=False, max_retries=0, timeout_seconds=120, rollback=Rollback.manual, run=_apply_run,
))
register(Tool(
    name="code.discard_session", version=1, permissions=["code:run"], side_effects=False,
    idempotent=True, max_retries=1, timeout_seconds=30, rollback=Rollback.none, run=_discard_run,
))
