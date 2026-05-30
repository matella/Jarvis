"""The plan executor — deterministic coordination over a validated plan (NOT an LLM loop).

Walks the plan's steps in dependency order, each action flowing through the existing
Intent→gate→executor (so mode, approval, audit all still apply); read steps run a query; advisory
steps are noted. The whole run shares the plan's `correlation_id`, so one `trace` shows the full
chain. Action-safety lives here: blast-radius + rate-limit pre-flight, and automatic rollback of
already-succeeded reversible steps when a later step truly fails.
"""

from __future__ import annotations

from typing import Any

from jarvis import db
from jarvis.core.planner import execution_order
from jarvis.core.policies import check_blast_radius, check_rate_limit
from jarvis.intents import service
from jarvis.intents.models import Intent, IntentReasoning, Risk
from jarvis.intents.repository import insert_intent
from jarvis.orchestration.models import Plan, PlanStatus, PlanStep, StepKind, StepStatus
from jarvis.orchestration.repository import get_plan, save_steps
from jarvis.tools.contract import Rollback
from jarvis.tools.registry import get_tool


class PlanNotFound(Exception):
    pass


def _read_query(conn: Any, capability: str, target: dict) -> str:
    """Execute a read-only plan step. Returns a short human summary stored on the step."""
    if capability == "read.state":
        rows = conn.execute("SELECT entity, status FROM state ORDER BY entity").fetchall()
        return f"{len(rows)} state rows"
    if capability == "read.incidents":
        row = conn.execute("SELECT count(*) AS n FROM incidents").fetchone()
        return f"{row['n']} incidents"
    if capability == "read.events":
        ent = target.get("entity")
        if ent:
            row = conn.execute(
                "SELECT count(*) AS n FROM events WHERE entity_ref = %s", (ent,)
            ).fetchone()
            return f"{row['n']} events for {ent}"
        row = conn.execute("SELECT count(*) AS n FROM events").fetchone()
        return f"{row['n']} events"
    if capability == "read.metrics":
        row = conn.execute("SELECT count(*) AS n FROM metrics").fetchone()
        return f"{row['n']} metric samples"
    return "ok"


def _make_intent(step: PlanStep, correlation_id: str) -> Intent:
    tool = get_tool(step.capability)
    # A fully-reversible action (rollback=automatic) is low-risk; otherwise medium. This is what
    # lets semi_autonomous auto-run the safe, undoable steps while still gating the rest.
    reversible = bool(tool and tool.rollback is not Rollback.none)
    auto_revertible = bool(tool and tool.rollback is Rollback.automatic)
    return Intent(
        type=step.capability,
        target=step.target,
        reasoning=IntentReasoning(
            summary=step.summary or step.capability, confidence=0.7,
            risk=Risk.low if auto_revertible else Risk.medium, reversible=reversible,
        ),
        requested_by="planner",
        requires_approval=bool(tool and tool.side_effects),
        correlation_id=correlation_id,
        causation_id=correlation_id,
    )


def _run_action(conn: Any, step: PlanStep, plan: Plan, *, simulate: bool) -> bool:
    """Run one action step through the gate. Returns True on a genuine failure (→ rollback+stop)."""
    tool = get_tool(step.capability)
    if simulate:
        preview = None
        if tool and tool.preview is not None:
            try:
                preview = tool.preview(step.target)
            except Exception as exc:  # noqa: BLE001
                preview = {"preview_error": str(exc)}
        step.status = StepStatus.skipped
        step.outcome = "simulated"
        step.detail = str(preview) if preview is not None else "would run (no preview)"
        return False

    intent = _make_intent(step, plan.correlation_id)
    insert_intent(conn, intent)
    step.intent_id = intent.intent_id
    try:
        execution = service.execute(conn, intent.intent_id)
    except service.ApprovalRequired:
        step.status = StepStatus.skipped
        step.outcome = "awaiting_approval"
        return False
    except service.ModeBlocked:
        step.status = StepStatus.skipped
        step.outcome = "frozen"
        return True  # maintenance — halt the plan

    step.outcome = execution.outcome.value
    if execution.outcome.value == "success":
        step.status = StepStatus.succeeded
        return False
    if execution.outcome.value == "skipped":
        step.status = StepStatus.skipped  # observe dry-run — expected, keep walking
        return False
    step.status = StepStatus.failed
    step.detail = execution.error
    return True  # real failure


def _rollback(succeeded: list[PlanStep]) -> None:
    """Revert already-succeeded steps whose tool declares rollback=automatic (newest first)."""
    for step in reversed(succeeded):
        tool = get_tool(step.capability)
        if tool and tool.rollback is Rollback.automatic and tool.revert is not None:
            try:
                tool.revert(step.target)
                step.status = StepStatus.rolled_back
            except Exception as exc:  # noqa: BLE001 — best-effort; record and continue
                step.detail = f"rollback failed: {exc}"


def execute_plan(plan_id: str, *, simulate: bool = False) -> Plan:
    """Walk a stored plan deterministically. `simulate` previews actions without touching infra."""
    with db.connect(autocommit=True) as conn:
        plan = get_plan(conn, plan_id)
        if plan is None:
            raise PlanNotFound(plan_id)

        check_blast_radius(plan.entities())
        action_steps = [s for s in plan.steps if s.kind is StepKind.action]
        if not simulate and action_steps:
            check_rate_limit(conn, planned_actions=len(action_steps))

        plan.status = PlanStatus.simulated if simulate else PlanStatus.running
        by_id = {s.id: s for s in plan.steps}
        succeeded_actions: list[PlanStep] = []
        failed = False

        for step in execution_order(plan.steps):
            if any(by_id[d].status in (StepStatus.failed, StepStatus.skipped) and
                   by_id[d].outcome not in ("simulated", "skipped", "awaiting_approval")
                   for d in step.depends_on):
                step.status = StepStatus.skipped
                step.outcome = "dependency_unmet"
                continue

            step.status = StepStatus.running
            if step.kind is StepKind.read:
                step.detail = _read_query(conn, step.capability, step.target)
                step.status = StepStatus.succeeded
            elif step.kind is StepKind.advisory:
                step.status = StepStatus.succeeded
                step.outcome = "noted"
                step.detail = f"advisory: {step.capability}"
            else:  # action
                if _run_action(conn, step, plan, simulate=simulate):
                    failed = True
                    _rollback(succeeded_actions)
                    break
                if step.status is StepStatus.succeeded:
                    succeeded_actions.append(step)

        if simulate:
            plan.status = PlanStatus.simulated
        else:
            plan.status = PlanStatus.failed if failed else PlanStatus.completed
        save_steps(conn, plan)
    return plan
