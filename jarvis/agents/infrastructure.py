"""Infrastructure agent — one-shot, proposes a structured Intent.

A specialized reasoning endpoint: given an entity's recent events + state, it emits ONE
JSON-constrained proposal. Deterministic code then validates it against the capability
registry before any Intent is persisted. The agent never executes anything.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from jarvis import db, ids
from jarvis.config import get_settings
from jarvis.core.assembly import assemble_context
from jarvis.core.context_store import get_context, save_context
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import emit_event
from jarvis.intents.models import Intent, IntentReasoning, Risk
from jarvis.intents.repository import get_intent, insert_intent
from jarvis.memory.store import MemoryStore
from jarvis.models import router
from jarvis.playbooks.models import Playbook
from jarvis.playbooks.repository import search_playbooks
from jarvis.tools.registry import get_tool, valid_intent_types

_WINDOW_HOURS = 24

_SYSTEM = (
    "You are Jarvis's infrastructure agent. Given recent events and state for one entity, "
    "decide whether an action is warranted. Respond with ONLY a JSON object: "
    '{"type": str, "target": object, "summary": str, "confidence": number 0-1, '
    '"risk": "low"|"medium"|"high", "reversible": bool}. '
    "Allowed types: 'docker.restart_container' (target {\"container\": name}) when a container "
    "is down/unhealthy and a restart is the safe, reversible fix; 'infra.investigate' or "
    "'infra.recommend' (target {}) when no direct action is warranted. "
    "If 'Relevant playbooks' are provided, follow their guidance. "
    "Base everything only on the provided events — never invent facts."
)


def _playbook_section(playbooks: list[Playbook]) -> str:
    if not playbooks:
        return ""
    lines = "\n".join(f"- {p.title}: {p.procedure}" for p in playbooks)
    return "\n\nRelevant playbooks:\n" + lines


class IntentProposal(BaseModel):
    type: str
    target: dict[str, Any] = Field(default_factory=dict)
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    risk: Risk
    reversible: bool


def _messages(prompt: str) -> list[dict]:
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": f"{prompt}\n\nRespond with the JSON proposal only."},
    ]


def _parse(content: str) -> IntentProposal:
    """Parse + validate the model's JSON. Raises ValueError at the boundary on bad output."""
    try:
        proposal = IntentProposal.model_validate_json(content)
    except ValidationError as exc:
        raise ValueError(f"proposal failed schema validation: {exc}") from exc
    if proposal.type not in valid_intent_types():
        raise ValueError(f"proposal type not a known capability: {proposal.type!r}")
    return proposal


def _trigger_event(conn, entity: str) -> Event | None:
    row = conn.execute(
        "SELECT * FROM events WHERE entity_ref = %s ORDER BY id DESC LIMIT 1", (entity,)
    ).fetchone()
    return Event(**row) if row else None


def propose_intent(entity: str, *, store: MemoryStore | None = None) -> Intent:
    """Run the agent over an entity and persist a validated proposed Intent."""
    settings = get_settings()
    since = utcnow() - timedelta(hours=_WINDOW_HOURS)

    with db.connect(autocommit=True) as conn:
        trigger = _trigger_event(conn, entity)
        correlation_id = trigger.correlation_id if trigger else ids.new_id(ids.CORRELATION)
        causation_id = trigger.id if trigger else None

        ctx = assemble_context(
            conn, since=since, entity=entity,
            query=f"should {entity} be acted on?", store=store,
        )
        # Procedural memory: retrieve operator playbooks relevant to this situation.
        try:
            pb_vec = router.embed(
                f"how to handle an issue with {entity}", correlation_id=correlation_id
            )
            playbooks = [pb for pb, _ in search_playbooks(conn, pb_vec, k=2)]
        except Exception:  # noqa: BLE001 — playbook retrieval is best-effort
            playbooks = []
        prompt = ctx.prompt + _playbook_section(playbooks)

        params = {"num_ctx": settings.inference_context, "keep_alive": settings.keep_alive}
        save_context(
            conn, context_ref=ctx.context_ref, prompt=prompt,
            model=settings.model_reasoning, params=params,
        )

        resp = router.chat(
            "reasoning", _messages(prompt),
            correlation_id=correlation_id, context_ref=ctx.context_ref, format="json",
        )
        proposal = _parse(str(resp["message"]["content"]))

        tool = get_tool(proposal.type)
        requires_approval = (tool.side_effects if tool else False) or proposal.risk is Risk.high

        intent = Intent(
            type=proposal.type,
            target=proposal.target,
            reasoning=IntentReasoning(
                summary=proposal.summary, confidence=proposal.confidence,
                risk=proposal.risk, reversible=proposal.reversible,
            ),
            requested_by="infrastructure_agent",
            context_ref=ctx.context_ref,
            requires_approval=requires_approval,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
        insert_intent(conn, intent)

    emit_event(
        Event(
            type="intent.proposed",
            severity=Severity.info,
            source="infrastructure_agent",
            entity_ref=f"intent:{intent.intent_id}",
            occurred_at=utcnow(),
            payload={"intent_type": intent.type, "requires_approval": intent.requires_approval},
            correlation_id=correlation_id,
            causation_id=intent.intent_id,
        )
    )
    return intent


def replay(intent_id: str) -> dict[str, Any]:
    """Re-run the model on the intent's STORED context and diff against the original.

    Inference is non-deterministic, so this reproduces the *inputs* (context_ref), not the
    decision — the new proposal may differ; that difference is the point.
    """
    with db.connect() as conn:
        intent = get_intent(conn, intent_id)
        if intent is None:
            raise ValueError(f"unknown intent: {intent_id}")
        if not intent.context_ref:
            raise ValueError(f"intent {intent_id} has no stored context_ref")
        ctx = get_context(conn, intent.context_ref)
    if ctx is None:
        raise ValueError(f"no stored context for {intent.context_ref}")

    resp = router.chat(
        "reasoning", _messages(ctx.prompt), context_ref=ctx.context_ref, format="json"
    )
    new = _parse(str(resp["message"]["content"]))
    return {
        "context_ref": ctx.context_ref,
        "model": ctx.model,
        "original": {
            "type": intent.type,
            "summary": intent.reasoning.summary,
            "confidence": intent.reasoning.confidence,
            "risk": intent.reasoning.risk.value,
        },
        "replayed": new.model_dump(mode="json"),
        "matches_type": new.type == intent.type,
    }
