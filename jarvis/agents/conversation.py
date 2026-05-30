"""The conversation/executive agent — one inference, one structured TurnResult.

NL + assembled context (recency + entity + vector + playbooks) + recent conversation memory +
a self-describing capability summary → a structured decision: *answer*, or *propose* a gated
Intent. It never executes; proposing routes through the existing M4 gate, and acting only happens
on an explicit confirmation in a later turn (`confirm-to-act`, handled in `respond`). External
content is data, not instructions — the deterministic boundary, not the model, enforces safety.
"""

from __future__ import annotations

import json
from datetime import timedelta
from enum import StrEnum
from typing import Any

import psycopg
from pydantic import BaseModel, Field, ValidationError

from jarvis import ids
from jarvis.conversation.store import Session, add_message, recent_messages
from jarvis.core.assembly import assemble_context
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import emit_event
from jarvis.intents.models import Intent, IntentReasoning, Risk
from jarvis.intents.repository import insert_intent
from jarvis.models import router
from jarvis.tools.registry import ADVISORY_TYPES, get_tool, valid_intent_types

_WINDOW_HOURS = 24
_AFFIRMATIVE = {"yes", "y", "yes please", "yep", "yeah", "do it", "go ahead", "confirm",
                "approved", "approve", "ok", "okay", "sure", "proceed"}
_NEGATIVE = {"no", "n", "nope", "cancel", "stop", "abort", "don't", "do not", "nevermind",
             "never mind", "reject"}


class TurnRoute(StrEnum):
    answer = "answer"
    propose = "propose"
    confirm = "confirm"
    cancel = "cancel"


class Citation(BaseModel):
    kind: str  # event | state | incident | playbook
    ref: str
    note: str = ""


class Artifact(BaseModel):
    kind: str  # table | metric | link | text
    title: str
    data: dict[str, Any] = Field(default_factory=dict)


class TurnResult(BaseModel):
    """The structured outcome of one conversational turn — what the UI renders."""

    route: TurnRoute
    message: str
    artifacts: list[Artifact] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    intent_id: str | None = None
    presence: str = "speaking"


class _Decision(BaseModel):
    """The model's raw structured output. `propose` fields are required only when proposing."""

    route: str = "answer"
    message: str = ""
    intent_type: str | None = None
    target: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = None
    risk: Risk = Risk.medium
    reversible: bool = True
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    citations: list[Citation] = Field(default_factory=list)


def capability_summary() -> str:
    """Self-describing capability registry — answers "what can you do?" and bounds the model."""
    lines = ["You can route a request to exactly one of these capabilities (Intent types):"]
    for name in valid_intent_types() - set(ADVISORY_TYPES):
        tool = get_tool(name)
        if tool is None:
            continue
        effect = "acts on infrastructure" if tool.side_effects else "read-only"
        lines.append(f"- {name}: {effect}, rollback={tool.rollback.value}")
    lines.append("Advisory (no infrastructure change): " + ", ".join(ADVISORY_TYPES))
    return "\n".join(lines)


def _is_affirmative(text: str) -> bool:
    return text.strip().lower().rstrip(".!") in _AFFIRMATIVE


def _is_negative(text: str) -> bool:
    return text.strip().lower().rstrip(".!") in _NEGATIVE


def _memory_window(conn: psycopg.Connection, session: Session) -> str:
    msgs = recent_messages(conn, session.conversation_id, limit=10)
    if not msgs:
        return ""
    rendered = "\n".join(f"{m['role']}: {m['content']}" for m in msgs)
    return "Recent conversation:\n" + rendered


def _build_prompt(ctx_prompt: str, memory: str, utterance: str) -> str:
    parts = [
        "You are Jarvis, an operational-intelligence assistant for a homelab. You reply with ONE "
        "JSON object and nothing else.\n"
        "ROUTING RULE (decide first):\n"
        "- If the user asks you to DO or CHANGE something (restart/stop/start/redeploy a "
        "container, edit a file, etc.), set route=\"propose\", pick the matching intent_type "
        "from the capabilities, and fill target. Do NOT perform it — a human confirms first.\n"
        "- Otherwise (a question, status request, explanation), set route=\"answer\" and put your "
        "grounded reply in message; cite events/state you used.\n"
        'Example — user "restart nginx" → {"route":"propose","intent_type":'
        '"docker.restart_container","target":{"container":"nginx"},"summary":"restart nginx",'
        '"message":"I can restart nginx.","risk":"medium","reversible":true,"confidence":0.9}.',
        capability_summary(),
    ]
    if memory:
        parts.append(memory)
    parts.append("Context:\n" + ctx_prompt)
    parts.append(f"User: {utterance}")
    parts.append(
        'Output exactly one JSON object with keys: route ("answer" or "propose"), '
        'message (string), and when route="propose": intent_type, target (object), summary, '
        'risk ("low"|"medium"|"high"), reversible (bool), confidence (0..1). '
        'Optional: citations [{kind, ref, note}]. No prose outside the JSON.'
    )
    return "\n\n".join(parts)


# Constrained-decoding schema: forces `route` to a present enum so a small model can't silently
# drop it (the failure we saw with bare format=json). Action fields stay optional.
_DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "route": {"type": "string", "enum": ["answer", "propose"]},
        "message": {"type": "string"},
        "intent_type": {"type": "string"},
        "target": {"type": "object"},
        "summary": {"type": "string"},
        "risk": {"type": "string", "enum": ["low", "medium", "high"]},
        "reversible": {"type": "boolean"},
        "confidence": {"type": "number"},
    },
    "required": ["route", "message"],
}


def _decide(prompt: str, *, correlation_id: str, context_ref: str) -> _Decision:
    """One inference → validated decision. Isolated so tests can monkeypatch the model."""
    resp = router.chat(
        "reasoning",
        [{"role": "user", "content": prompt}],
        correlation_id=correlation_id, context_ref=context_ref, format=_DECISION_SCHEMA,
    )
    raw = str(resp["message"]["content"])
    try:
        decision = _Decision.model_validate_json(raw)
        if decision.message or decision.route == "propose":
            return decision
    except ValidationError:
        pass
    # The model emitted JSON that doesn't match our schema (qwen often invents its own shape under
    # format=json). Salvage a human-readable message rather than dumping raw JSON at the user.
    return _Decision(route="answer", message=_salvage_message(raw))


def _salvage_message(raw: str) -> str:
    """Best-effort readable text from an off-schema JSON (or plain) model reply."""
    try:
        data = json.loads(raw)
    except Exception:
        return raw.strip()[:2000] or "(no response)"
    if isinstance(data, str):
        return data[:2000]
    if isinstance(data, dict):
        for key in ("message", "answer", "response", "reply", "summary", "text"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return val[:2000]
        # Fall back to a compact "key: value" rendering of scalar fields.
        parts = [f"{k}: {v}" for k, v in data.items() if isinstance(v, (str, int, float, bool))]
        if parts:
            return "\n".join(parts)[:2000]
    return raw.strip()[:2000] or "(no response)"


def respond(
    conn: psycopg.Connection, session: Session, utterance: str, *, store: Any = None
) -> TurnResult:
    """Process one user turn end-to-end: persist, reason/route, maybe propose, emit, return."""
    add_message(conn, session.conversation_id, role="user", content=utterance)

    # confirm-to-act: a pending proposal + an affirmative/negative reply short-circuits the model.
    if session.pending_intent_id and _is_affirmative(utterance):
        result = _confirm(conn, session)
    elif session.pending_intent_id and _is_negative(utterance):
        result = _cancel(session)
    else:
        result = _reason(conn, session, utterance, store=store)

    add_message(
        conn, session.conversation_id, role="assistant", content=result.message,
        artifacts={"route": result.route.value, "intent_id": result.intent_id},
    )
    emit_event(
        Event(
            type="conversation.message", severity=Severity.info, source="conversation",
            entity_ref=f"conversation:{session.conversation_id}", occurred_at=utcnow(),
            payload={"actor": session.actor, "route": result.route.value,
                     "intent_id": result.intent_id},
            correlation_id=ids.new_id(ids.CORRELATION),
        )
    )
    return result


def _reason(
    conn: psycopg.Connection, session: Session, utterance: str, *, store: Any
) -> TurnResult:
    since = utcnow() - timedelta(hours=_WINDOW_HOURS)
    ctx = assemble_context(conn, since=since, query=utterance, store=store)
    prompt = _build_prompt(ctx.prompt, _memory_window(conn, session), utterance)
    decision = _decide(
        prompt, correlation_id=ids.new_id(ids.CORRELATION), context_ref=ctx.context_ref
    )

    if decision.route == "propose" and decision.intent_type in valid_intent_types():
        intent = _make_intent(decision, ctx.context_ref, session.actor)
        insert_intent(conn, intent)
        session.pending_intent_id = intent.intent_id
        tool = get_tool(intent.type)
        verb = "act on infrastructure" if (tool and tool.side_effects) else "run"
        msg = decision.message or f"I can {verb} via `{intent.type}`."
        msg += " Confirm to proceed (reply 'yes'), or 'no' to cancel."
        return TurnResult(
            route=TurnRoute.propose, message=msg, intent_id=intent.intent_id,
            citations=decision.citations,
        )

    return TurnResult(
        route=TurnRoute.answer, message=decision.message or "(no response)",
        citations=decision.citations,
    )


def _make_intent(decision: _Decision, context_ref: str, actor: str) -> Intent:
    tool = get_tool(decision.intent_type or "")
    requires_approval = (tool.side_effects if tool else False) or decision.risk is Risk.high
    return Intent(
        type=decision.intent_type or "",
        target=decision.target,
        reasoning=IntentReasoning(
            summary=decision.summary or decision.message or decision.intent_type or "",
            confidence=decision.confidence, risk=decision.risk, reversible=decision.reversible,
        ),
        requested_by=f"user:{actor}",
        context_ref=context_ref,
        requires_approval=requires_approval,
        correlation_id=ids.new_id(ids.CORRELATION),
    )


def _confirm(conn: psycopg.Connection, session: Session) -> TurnResult:
    from jarvis.audit.log import record
    from jarvis.intents import service

    intent_id = session.pending_intent_id
    session.pending_intent_id = None
    try:
        service.approve(conn, intent_id)
        record(conn, actor=f"user:{session.actor}", action="intent.approve", target=intent_id)
        execution = service.execute(conn, intent_id)
        record(conn, actor=f"user:{session.actor}", action="intent.execute",
               target=intent_id, outcome=execution.outcome.value)
        return TurnResult(
            route=TurnRoute.confirm,
            message=f"Done — executed `{intent_id}` → {execution.outcome.value}.",
            intent_id=intent_id,
        )
    except service.ModeBlocked as exc:
        return TurnResult(route=TurnRoute.confirm,
                          message=f"Blocked by operational mode: {exc}", intent_id=intent_id)
    except service.ApprovalRequired as exc:
        return TurnResult(
            route=TurnRoute.confirm,
            message=f"Approved, but execution still gated: {exc}", intent_id=intent_id,
        )


def _cancel(session: Session) -> TurnResult:
    intent_id = session.pending_intent_id
    session.pending_intent_id = None
    return TurnResult(route=TurnRoute.cancel, message="Cancelled — nothing was run.",
                      intent_id=intent_id)
