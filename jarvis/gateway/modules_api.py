"""Personal-OS module REST — operator-direct CRUD + reads for the app shell's panels.

The operator is authenticated (session), so they ARE the human gate: personal-data writes go through
the module repository, and operator-triggered gated actions (research run, recipe import, code
session) reuse the registered tool's deterministic `run` (the authenticated click is the consent).
GETs need `read`; writes/actions need `chat`. Datetime fields accept ISO-8601 (Pydantic coerces).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from jarvis import db
from jarvis.gateway.auth import Principal
from jarvis.gateway.deps import principal as _principal
from jarvis.gateway.deps import require as _require

router = APIRouter(prefix="/api")


def _dump(model: Any) -> dict:
    return model.model_dump(mode="json")


def _dump_all(models: list) -> list[dict]:
    return [m.model_dump(mode="json") for m in models]


def _build(model_cls, body: dict, allowed: tuple[str, ...]):
    try:
        return model_cls(**{k: body[k] for k in allowed if k in body})
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── Tasks ─────────────────────────────────────────────────────────────────────────────────────
@router.get("/tasks")
def list_tasks(p: Principal = Depends(_principal)) -> list[dict]:
    _require(p, "read")
    from jarvis.tasks import repository
    with db.connect() as conn:
        return _dump_all(repository.list_open(conn))


@router.post("/tasks")
def create_task(body: dict, p: Principal = Depends(_principal)) -> dict:
    _require(p, "chat")
    from jarvis.tasks import repository
    from jarvis.tasks.models import Task
    task = _build(Task, body, ("title", "notes", "priority", "due_at", "source_entity_ref"))
    with db.connect() as conn:
        return _dump(repository.create(conn, task))


@router.patch("/tasks/{task_id}")
def update_task(task_id: str, body: dict, p: Principal = Depends(_principal)) -> dict:
    _require(p, "chat")
    from jarvis.tasks import repository
    from jarvis.tasks.models import TaskPriority, TaskStatus
    fields: dict = {}
    if "title" in body:
        fields["title"] = body["title"]
    if "notes" in body:
        fields["notes"] = body["notes"]
    if "status" in body:
        fields["status"] = TaskStatus(body["status"])
    if "priority" in body:
        fields["priority"] = TaskPriority(body["priority"])
    if "due_at" in body:
        fields["due_at"], fields["set_due"] = body["due_at"], True
    with db.connect() as conn:
        updated = repository.update(conn, task_id, **fields)
    if updated is None:
        raise HTTPException(404, "task not found")
    return _dump(updated)


@router.post("/tasks/{task_id}/complete")
def complete_task(task_id: str, p: Principal = Depends(_principal)) -> dict:
    _require(p, "chat")
    from jarvis.tasks import repository
    with db.connect() as conn:
        done = repository.complete(conn, task_id)
    if done is None:
        raise HTTPException(404, "task not found")
    return _dump(done)


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str, p: Principal = Depends(_principal)) -> dict:
    _require(p, "chat")
    from jarvis.tasks import repository
    with db.connect() as conn:
        ok = repository.delete(conn, task_id)
    if not ok:
        raise HTTPException(404, "task not found")
    return {"ok": True}


# ── Notes ─────────────────────────────────────────────────────────────────────────────────────
@router.get("/notes")
def list_notes(p: Principal = Depends(_principal)) -> list[dict]:
    _require(p, "read")
    from jarvis.notes import repository
    with db.connect() as conn:
        return _dump_all(repository.recent(conn))


@router.post("/notes")
def create_note(body: dict, p: Principal = Depends(_principal)) -> dict:
    _require(p, "chat")
    from jarvis.notes import repository
    from jarvis.notes.models import Note
    note = _build(Note, body, ("title", "body_md", "tags", "pinned", "source_entity_ref"))
    with db.connect() as conn:
        return _dump(repository.create(conn, note))


@router.patch("/notes/{note_id}")
def update_note(note_id: str, body: dict, p: Principal = Depends(_principal)) -> dict:
    _require(p, "chat")
    from jarvis.notes import repository
    fields = {k: body[k] for k in ("title", "body_md", "pinned", "tags") if k in body}
    with db.connect() as conn:
        updated = repository.update(conn, note_id, **fields)
    if updated is None:
        raise HTTPException(404, "note not found")
    return _dump(updated)


@router.delete("/notes/{note_id}")
def delete_note(note_id: str, p: Principal = Depends(_principal)) -> dict:
    _require(p, "chat")
    from jarvis.notes import repository
    with db.connect() as conn:
        ok = repository.delete(conn, note_id)
    if not ok:
        raise HTTPException(404, "note not found")
    return {"ok": True}


# ── Documents ─────────────────────────────────────────────────────────────────────────────────
@router.get("/documents")
def list_documents(p: Principal = Depends(_principal)) -> list[dict]:
    _require(p, "read")
    from jarvis.documents import repository
    with db.connect() as conn:
        return _dump_all(repository.recent(conn))


@router.get("/documents/{doc_id}")
def get_document(doc_id: str, p: Principal = Depends(_principal)) -> dict:
    _require(p, "read")
    from jarvis.documents import repository
    with db.connect() as conn:
        doc = repository.get(conn, doc_id)
        if doc is None:
            raise HTTPException(404, "document not found")
        return {"document": _dump(doc), "versions": _dump_all(repository.versions(conn, doc_id))}


@router.post("/documents")
def create_document(body: dict, p: Principal = Depends(_principal)) -> dict:
    _require(p, "chat")
    from jarvis.documents import repository
    from jarvis.documents.models import Document
    doc = _build(Document, body, ("title", "body_md", "source_entity_ref"))
    with db.connect() as conn:
        return _dump(repository.create(conn, doc))


@router.patch("/documents/{doc_id}")
def update_document(doc_id: str, body: dict, p: Principal = Depends(_principal)) -> dict:
    _require(p, "chat")
    from jarvis.documents import repository
    from jarvis.documents.models import DocStatus
    fields: dict = {k: body[k] for k in ("title", "body_md") if k in body}
    if "status" in body:
        fields["status"] = DocStatus(body["status"])
    with db.connect() as conn:
        updated = repository.update(conn, doc_id, **fields)
    if updated is None:
        raise HTTPException(404, "document not found")
    return _dump(updated)


@router.post("/documents/{doc_id}/ai-edit")
def document_ai_edit(doc_id: str, body: dict, p: Principal = Depends(_principal)) -> dict:
    _require(p, "chat")
    from jarvis.cookbook import backend_for_action
    from jarvis.documents import ai, repository
    instruction = str(body.get("instruction", ""))
    with db.connect() as conn:
        doc = repository.get(conn, doc_id)
    if doc is None:
        raise HTTPException(404, "document not found")
    try:
        proposal = ai.propose_edit(
            body_md=doc.body_md, instruction=instruction, selection=body.get("selection"),
            backend=backend_for_action("document.ai_edit"),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"proposal": proposal}  # the UI shows a diff; accept → PATCH /documents/{id}


@router.post("/documents/{doc_id}/restore")
def restore_document(doc_id: str, body: dict, p: Principal = Depends(_principal)) -> dict:
    _require(p, "chat")
    from jarvis.documents import repository
    with db.connect() as conn:
        restored = repository.restore(conn, doc_id, str(body.get("version_id", "")))
    if restored is None:
        raise HTTPException(404, "document or version not found")
    return _dump(restored)


# ── Recipes ───────────────────────────────────────────────────────────────────────────────────
@router.get("/recipes")
def list_recipes(p: Principal = Depends(_principal)) -> list[dict]:
    _require(p, "read")
    from jarvis.recipes import repository
    with db.connect() as conn:
        return _dump_all(repository.recent(conn))


@router.post("/recipes")
def create_recipe(body: dict, p: Principal = Depends(_principal)) -> dict:
    _require(p, "chat")
    from jarvis.recipes import repository
    from jarvis.recipes.models import Recipe
    recipe = _build(Recipe, body, ("title", "servings", "ingredients", "steps", "tags", "notes_md"))
    with db.connect() as conn:
        return _dump(repository.create(conn, recipe))


@router.delete("/recipes/{recipe_id}")
def delete_recipe(recipe_id: str, p: Principal = Depends(_principal)) -> dict:
    _require(p, "chat")
    from jarvis.recipes import repository
    with db.connect() as conn:
        ok = repository.delete(conn, recipe_id)
    if not ok:
        raise HTTPException(404, "recipe not found")
    return {"ok": True}


@router.post("/recipes/import")
def import_recipe_url(body: dict, p: Principal = Depends(_principal)) -> dict:
    _require(p, "chat")
    return _run_tool("recipe.import_url", {"url": body.get("url")})


@router.post("/recipes/{recipe_id}/shopping-list")
def recipe_shopping_list(recipe_id: str, p: Principal = Depends(_principal)) -> dict:
    _require(p, "chat")
    return _run_tool("recipe.to_shopping_list", {"id": recipe_id})


# ── Calendar ──────────────────────────────────────────────────────────────────────────────────
@router.get("/calendar")
def list_calendar(start: str, end: str, p: Principal = Depends(_principal)) -> list[dict]:
    _require(p, "read")
    from datetime import datetime

    from jarvis.calendar import repository
    try:
        s, e = datetime.fromisoformat(start), datetime.fromisoformat(end)
    except ValueError as exc:
        raise HTTPException(400, "start/end must be ISO-8601") from exc
    with db.connect() as conn:
        return _dump_all(repository.agenda(conn, s, e))


@router.post("/calendar")
def create_event(body: dict, p: Principal = Depends(_principal)) -> dict:
    _require(p, "chat")
    from jarvis.calendar import repository
    from jarvis.calendar.models import CalendarEvent
    event = _build(CalendarEvent, body,
                   ("title", "starts_at", "ends_at", "location", "description", "all_day",
                    "source_entity_ref"))
    with db.connect() as conn:
        return _dump(repository.create_local(conn, event))


@router.delete("/calendar/{event_id}")
def delete_event(event_id: str, p: Principal = Depends(_principal)) -> dict:
    _require(p, "chat")
    from jarvis.calendar import repository
    with db.connect() as conn:
        try:
            ok = repository.delete_local(conn, event_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    if not ok:
        raise HTTPException(404, "event not found")
    return {"ok": True}


# ── Research ──────────────────────────────────────────────────────────────────────────────────
@router.get("/research")
def list_research(p: Principal = Depends(_principal)) -> list[dict]:
    _require(p, "read")
    from jarvis.research import repository
    with db.connect() as conn:
        return _dump_all(repository.recent(conn))


@router.post("/research")
def run_research(body: dict, p: Principal = Depends(_principal)) -> dict:
    _require(p, "chat")  # operator-triggered = consent; reuses the gated tool's deterministic run
    return _run_tool("research.run", {"query": body.get("query"), "depth": body.get("depth",
                                                                                    "standard")})


# ── Mail ──────────────────────────────────────────────────────────────────────────────────────
@router.get("/mail")
def list_mail(p: Principal = Depends(_principal)) -> list[dict]:
    _require(p, "read")
    from jarvis.mail import repository
    with db.connect() as conn:
        return _dump_all(repository.recent(conn))


@router.get("/mail/{mail_id}")
def get_mail(mail_id: str, p: Principal = Depends(_principal)) -> dict:
    _require(p, "read")
    from jarvis.mail import repository
    with db.connect() as conn:
        msg = repository.get(conn, mail_id)
    if msg is None:
        raise HTTPException(404, "message not found")
    return _dump(msg)  # includes the full body_text + to_addrs + triage


@router.post("/mail/send")
def send_mail(body: dict, p: Principal = Depends(_principal)) -> dict:
    _require(p, "chat")  # gated tool; the authenticated operator clicking Send is the consent
    return _run_tool("mail.send", {"to": body.get("to"), "subject": body.get("subject"),
                                   "body": body.get("body")})


@router.post("/mail/{mail_id}/draft")
def draft_mail(mail_id: str, body: dict, p: Principal = Depends(_principal)) -> dict:
    _require(p, "chat")
    from jarvis.cookbook import backend_for_action
    from jarvis.mail import compose, repository
    with db.connect() as conn:
        msg = repository.get(conn, mail_id)
    if msg is None:
        raise HTTPException(404, "message not found")
    try:
        draft = compose.draft_reply(
            original_subject=msg.subject, original_body=msg.body_text or msg.snippet,
            instruction=str(body.get("instruction", "")),
            backend=backend_for_action("mail.draft"),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"draft": draft}


# ── Model cookbook ────────────────────────────────────────────────────────────────────────────
@router.get("/models/prefs")
def list_model_prefs(p: Principal = Depends(_principal)) -> list[dict]:
    _require(p, "read")
    from jarvis.cookbook import repository
    with db.connect() as conn:
        return _dump_all(repository.list_prefs(conn))


@router.put("/models/prefs")
def set_model_pref(body: dict, p: Principal = Depends(_principal)) -> dict:
    _require(p, "chat")
    from jarvis.cookbook.models import ModelPref, PrefScope
    from jarvis.cookbook.repository import set_pref
    try:
        pref = ModelPref(scope=PrefScope.action, scope_key=str(body["action"]),
                         backend=str(body["backend"]))
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, f"need action + valid backend: {exc}") from exc
    with db.connect() as conn:
        return _dump(set_pref(conn, pref))


@router.post("/models/preset")
def apply_model_preset(body: dict, p: Principal = Depends(_principal)) -> dict:
    _require(p, "chat")
    from jarvis.cookbook.repository import apply_preset
    try:
        with db.connect() as conn:
            n = apply_preset(conn, str(body.get("name", "")))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"applied": n}


# ── Code (OpenCode) ───────────────────────────────────────────────────────────────────────────
@router.get("/code")
def list_code_sessions(p: Principal = Depends(_principal)) -> list[dict]:
    _require(p, "read")
    from jarvis.code import repository
    with db.connect() as conn:
        return _dump_all(repository.recent(conn))


@router.get("/code/{session_id}")
def get_code_session(session_id: str, p: Principal = Depends(_principal)) -> dict:
    _require(p, "read")
    from jarvis.code import repository
    with db.connect() as conn:
        session = repository.get(conn, session_id)
    if session is None:
        raise HTTPException(404, "code session not found")
    return _dump(session)


@router.post("/code/start")
def start_code_session(body: dict, p: Principal = Depends(_principal)) -> dict:
    _require(p, "chat")
    return _run_tool("code.start_session", {"repo_path": body.get("repo_path"),
                                            "task": body.get("task"),
                                            "base_ref": body.get("base_ref", "HEAD")})


@router.post("/code/{session_id}/apply")
def apply_code_session(session_id: str, p: Principal = Depends(_principal)) -> dict:
    _require(p, "chat")
    return _run_tool("code.apply_patch", {"session_id": session_id})


@router.post("/code/{session_id}/discard")
def discard_code_session(session_id: str, p: Principal = Depends(_principal)) -> dict:
    _require(p, "chat")
    return _run_tool("code.discard_session", {"session_id": session_id})


# ── Facts (Memories UI minimal) ───────────────────────────────────────────────────────────────
@router.get("/facts")
def list_facts(p: Principal = Depends(_principal)) -> list[dict]:
    _require(p, "read")
    from jarvis.memory.facts import list_facts as _list
    with db.connect() as conn:
        return [{"key": f.key, "value": f.value} for f in _list(conn)]


@router.post("/facts")
def set_fact(body: dict, p: Principal = Depends(_principal)) -> dict:
    _require(p, "chat")
    from jarvis.memory.facts import set_fact as _set
    try:
        with db.connect() as conn:
            fact = _set(conn, str(body.get("key", "")), str(body.get("value", "")))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"key": fact.key, "value": fact.value}


# ── Routines (operational surface) ────────────────────────────────────────────────────────────
@router.get("/routines")
def list_routines_api(p: Principal = Depends(_principal)) -> list[dict]:
    _require(p, "read")
    from jarvis.routines.repository import list_routines
    with db.connect() as conn:
        return [
            {"id": r.id, "name": r.name, "enabled": r.enabled,
             "schedule": r.schedule.model_dump(mode="json"),
             "action": r.action.model_dump(mode="json"),
             "last_run": r.last_run.isoformat() if r.last_run else None}
            for r in list_routines(conn)
        ]


@router.post("/routines/{routine_id}/{op}")
def routine_op(routine_id: str, op: str, p: Principal = Depends(_principal)) -> dict:
    _require(p, "chat")
    from jarvis.routines.repository import get_routine, set_enabled
    if op in ("enable", "disable"):
        with db.connect(autocommit=True) as conn:
            if not set_enabled(conn, routine_id, op == "enable"):
                raise HTTPException(404, "routine not found")
        return {"id": routine_id, "enabled": op == "enable"}
    if op == "run":
        from jarvis.routines.scheduler import run_routine
        with db.connect() as conn:
            routine = get_routine(conn, routine_id)
        if routine is None:
            raise HTTPException(404, "routine not found")
        return {"id": routine_id, "ran": True, "preview": run_routine(routine)[:500]}
    raise HTTPException(400, f"unknown op: {op} (enable|disable|run)")


def _run_tool(name: str, target: dict[str, Any]) -> dict[str, Any]:
    """Run a registered tool's deterministic executor on behalf of the authenticated operator.

    The operator's authenticated request IS the human gate (Hard Rule #1's gate is graded, not the
    boundary — the LLM still never calls this). Validation errors → 400; tool failures → 502.
    """
    from jarvis.tools.registry import get_tool
    tool = get_tool(name)
    if tool is None:
        raise HTTPException(404, f"unknown tool: {name}")
    try:
        return tool.run({k: v for k, v in target.items() if v is not None},
                        timeout_s=tool.timeout_seconds)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — surface tool failure without leaking a stack trace
        raise HTTPException(502, f"{type(exc).__name__}: {exc}") from exc
