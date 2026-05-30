"""The planner — ONE inference turns a goal into a validated plan DAG of known capabilities.

Hard Rule 2 intact: the model plans once (no loop, no agent↔agent chat); every step is validated
against the capability registry before anything runs, and coordination is deterministic code
(core/plan_executor.py). An unknown capability rejects the whole plan — the model can only compose
things the system already knows how to do.
"""

from __future__ import annotations

import json

from jarvis import db, ids
from jarvis.config import get_settings
from jarvis.core.context_store import save_context
from jarvis.models import router
from jarvis.orchestration.models import Plan, PlanStatus, PlanStep, StepKind
from jarvis.orchestration.repository import insert_plan
from jarvis.tools.registry import ADVISORY_TYPES, capabilities

# Read-only queries the planner may use (no gate); executed deterministically by the executor.
READ_CAPABILITIES = ("read.state", "read.incidents", "read.events", "read.metrics")


class PlanRejected(Exception):
    """A proposed plan failed validation (unknown capability or bad DAG); it is stored rejected."""


_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "kind": {"type": "string", "enum": ["action", "read", "advisory"]},
                    "capability": {"type": "string"},
                    "target": {"type": "object"},
                    "summary": {"type": "string"},
                    "depends_on": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id", "kind", "capability"],
            },
        },
    },
    "required": ["steps"],
}


def _catalog() -> str:
    actions = ", ".join(sorted(capabilities())) or "(none)"
    return (
        "Capabilities you may compose (use the exact names):\n"
        f"- action (changes infra, gated): {actions}\n"
        f"- read (read-only queries): {', '.join(READ_CAPABILITIES)}\n"
        f"- advisory (agent reasoning, no change): {', '.join(ADVISORY_TYPES)}"
    )


def _prompt(goal: str) -> str:
    return (
        "You are Jarvis's planner. Break the goal into the FEWEST ordered steps using ONLY the "
        "listed capabilities. Diagnose with read/advisory steps before any action. Each step: a "
        "unique id (s1,s2,…), kind, the exact capability name, a target object (e.g. "
        '{"container":"nginx"}), and depends_on (ids of prerequisite steps).\n\n'
        f"{_catalog()}\n\nGoal: {goal}\n\n"
        'Reply with JSON {"steps":[{"id","kind","capability","target","summary","depends_on"}]}. '
        "Do not invent capabilities; if the goal needs none, return an empty steps list."
    )


def _valid_capability(step: PlanStep) -> bool:
    if step.kind is StepKind.action:
        return step.capability in capabilities()
    if step.kind is StepKind.read:
        return step.capability in READ_CAPABILITIES
    return step.capability in ADVISORY_TYPES


def _validate(plan: Plan) -> None:
    """Reject unknown capabilities, dangling deps, cycles, or oversized plans (→ PlanRejected)."""
    s = get_settings()
    if len(plan.steps) > s.plan_max_steps:
        raise PlanRejected(f"plan has {len(plan.steps)} steps (limit {s.plan_max_steps})")
    ids_seen = {step.id for step in plan.steps}
    if len(ids_seen) != len(plan.steps):
        raise PlanRejected("duplicate step ids")
    for step in plan.steps:
        if not _valid_capability(step):
            raise PlanRejected(f"unknown {step.kind.value} capability: {step.capability!r}")
        for dep in step.depends_on:
            if dep not in ids_seen:
                raise PlanRejected(f"step {step.id} depends on unknown step {dep!r}")
    _toposort(plan.steps)  # raises on a cycle


def _toposort(steps: list[PlanStep]) -> list[PlanStep]:
    """Kahn's algorithm — a valid execution order; raises PlanRejected on a cycle."""
    by_id = {s.id: s for s in steps}
    indeg = {s.id: 0 for s in steps}
    for s in steps:
        for _dep in s.depends_on:
            indeg[s.id] += 1
    ready = [sid for sid, d in indeg.items() if d == 0]
    order: list[str] = []
    while ready:
        sid = ready.pop(0)
        order.append(sid)
        for s in steps:
            if sid in s.depends_on:
                indeg[s.id] -= 1
                if indeg[s.id] == 0:
                    ready.append(s.id)
    if len(order) != len(steps):
        raise PlanRejected("plan dependency cycle")
    return [by_id[sid] for sid in order]


def execution_order(steps: list[PlanStep]) -> list[PlanStep]:
    """Public: a dependency-respecting order for the executor."""
    return _toposort(steps)


def _decide(goal: str, *, correlation_id: str, context_ref: str) -> list[PlanStep]:
    resp = router.chat(
        "reasoning", [{"role": "user", "content": _prompt(goal)}],
        correlation_id=correlation_id, context_ref=context_ref, format=_PLAN_SCHEMA,
    )
    raw = str(resp["message"]["content"])
    try:
        data = json.loads(raw)
        return [PlanStep(**s) for s in data.get("steps", [])]
    except Exception as exc:  # noqa: BLE001 — a malformed plan is a rejected plan, not a crash
        raise PlanRejected(f"planner returned unparseable steps: {exc}") from exc


def plan(goal: str, *, store: bool = True) -> Plan:
    """Produce, validate and persist a Plan for `goal`. Raises PlanRejected on invalid output."""
    settings = get_settings()
    correlation_id = ids.new_id(ids.CORRELATION)
    context_ref = "ctx_plan_" + ids.new_id(ids.CONTEXT).split("_", 1)[1][:16]

    prompt = _prompt(goal)
    with db.connect(autocommit=True) as conn:
        save_context(
            conn, context_ref=context_ref, prompt=prompt,
            model=settings.model_reasoning,
            params={"num_ctx": settings.inference_context, "format": "plan_schema"},
        )
        steps = _decide(goal, correlation_id=correlation_id, context_ref=context_ref)
        plan_obj = Plan(
            goal=goal, steps=steps, context_ref=context_ref, correlation_id=correlation_id,
        )
        try:
            _validate(plan_obj)
        except PlanRejected:
            plan_obj.status = PlanStatus.rejected
            if store:
                insert_plan(conn, plan_obj)
            raise
        if store:
            insert_plan(conn, plan_obj)
    return plan_obj
