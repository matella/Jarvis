"""7 unit: plan validation + dependency ordering (no DB, no model)."""

from __future__ import annotations

import pytest

from jarvis.core.planner import PlanRejected, _validate, execution_order
from jarvis.orchestration.models import Plan, PlanStep, StepKind


def _plan(steps: list[PlanStep]) -> Plan:
    return Plan(goal="g", steps=steps, correlation_id="corr_x")


def _step(sid: str, cap: str, kind: StepKind = StepKind.read, deps=None) -> PlanStep:
    return PlanStep(id=sid, kind=kind, capability=cap, depends_on=deps or [])


def test_known_capabilities_validate() -> None:
    plan = _plan([
        _step("s1", "read.state"),
        _step("s2", "infra.investigate", StepKind.advisory, ["s1"]),
        _step("s3", "docker.restart_container", StepKind.action, ["s2"]),
    ])
    _validate(plan)  # no raise


def test_unknown_action_capability_rejected() -> None:
    plan = _plan([_step("s1", "docker.delete_everything", StepKind.action)])
    with pytest.raises(PlanRejected, match="unknown action capability"):
        _validate(plan)


def test_unknown_read_capability_rejected() -> None:
    plan = _plan([_step("s1", "read.world_domination")])
    with pytest.raises(PlanRejected, match="unknown read capability"):
        _validate(plan)


def test_dangling_dependency_rejected() -> None:
    plan = _plan([_step("s1", "read.state", deps=["s9"])])
    with pytest.raises(PlanRejected, match="unknown step"):
        _validate(plan)


def test_duplicate_ids_rejected() -> None:
    plan = _plan([_step("s1", "read.state"), _step("s1", "read.events")])
    with pytest.raises(PlanRejected, match="duplicate step ids"):
        _validate(plan)


def test_cycle_rejected() -> None:
    plan = _plan([
        _step("s1", "read.state", deps=["s2"]),
        _step("s2", "read.events", deps=["s1"]),
    ])
    with pytest.raises(PlanRejected, match="cycle"):
        _validate(plan)


def test_oversized_plan_rejected() -> None:
    steps = [_step(f"s{i}", "read.state") for i in range(50)]
    with pytest.raises(PlanRejected, match="steps"):
        _validate(_plan(steps))


def test_execution_order_respects_dependencies() -> None:
    steps = [
        _step("s3", "docker.restart_container", StepKind.action, ["s2"]),
        _step("s1", "read.state"),
        _step("s2", "infra.recommend", StepKind.advisory, ["s1"]),
    ]
    order = [s.id for s in execution_order(steps)]
    assert order.index("s1") < order.index("s2") < order.index("s3")
