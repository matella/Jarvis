"""7 integration: the deterministic plan executor over the live DB.

Two acceptance paths: (1) a 2–3 step plan over real capabilities walks step-by-step under observe
(every action a dry-run, nothing touched), one shared correlation_id; (2) with fake auto-revertible
tools under semi_autonomous, a forced failure in a later step rolls back the already-succeeded one.
"""

from __future__ import annotations

import psycopg
import pytest

from jarvis.core import policies
from jarvis.core.modes import Mode, get_mode, set_mode
from jarvis.core.plan_executor import execute_plan
from jarvis.orchestration.models import Plan, PlanStatus, PlanStep, StepKind, StepStatus
from jarvis.orchestration.repository import insert_plan
from jarvis.tools.contract import Rollback, Tool
from jarvis.tools.registry import _REGISTRY, register

pytestmark = pytest.mark.integration


def _cleanup(conn: psycopg.Connection, corr: str) -> None:
    conn.execute("DELETE FROM executions WHERE correlation_id = %s", (corr,))
    conn.execute("DELETE FROM intents WHERE correlation_id = %s", (corr,))
    conn.execute("DELETE FROM plans WHERE correlation_id = %s", (corr,))


def test_plan_walks_under_observe_dry_run(db_conn: psycopg.Connection) -> None:
    corr = "corr_plan_itest_obs"
    plan = Plan(
        goal="diagnose nginx and restart if needed", correlation_id=corr,
        steps=[
            PlanStep(id="s1", kind=StepKind.read, capability="read.state"),
            PlanStep(id="s2", kind=StepKind.advisory, capability="infra.investigate",
                     depends_on=["s1"]),
            PlanStep(id="s3", kind=StepKind.action, capability="docker.restart_container",
                     target={"container": "nginx"}, depends_on=["s2"]),
        ],
    )
    original = get_mode(db_conn)
    set_mode(db_conn, Mode.observe)
    try:
        insert_plan(db_conn, plan)
        done = execute_plan(plan.plan_id)
        assert done.status is PlanStatus.completed
        by_id = {s.id: s for s in done.steps}
        assert by_id["s1"].status is StepStatus.succeeded  # read ran
        assert by_id["s2"].status is StepStatus.succeeded  # advisory noted
        # the side-effecting action is gated, not executed: a real Intent was created and held for
        # approval (nothing touched infra) — the plan walked the whole DAG safely.
        assert by_id["s3"].status is StepStatus.skipped
        assert by_id["s3"].outcome == "awaiting_approval"
        assert by_id["s3"].intent_id is not None
    finally:
        set_mode(db_conn, original)
        _cleanup(db_conn, corr)


def test_failure_rolls_back_succeeded_reversible_step(
    db_conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    reverted: list[str] = []
    register(Tool(
        name="test.ok_revertible", version=1, permissions=[], side_effects=True, idempotent=True,
        max_retries=0, timeout_seconds=5, rollback=Rollback.automatic,
        run=lambda target, **_k: {"ran": target},
        revert=lambda target: reverted.append(str(target)) or {"reverted": target},
    ))
    register(Tool(
        name="test.boom", version=1, permissions=[], side_effects=True, idempotent=True,
        max_retries=0, timeout_seconds=5, rollback=Rollback.automatic,
        run=lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")),
    ))

    # keep the rate limiter out of the way (earlier runs may have logged executions)
    class _Cfg:
        action_rate_limit = 1000
        action_rate_window_s = 300
        plan_max_entities = 5
    monkeypatch.setattr(policies, "get_settings", lambda: _Cfg())

    corr = "corr_plan_itest_rollback"
    plan = Plan(
        goal="do two reversible things; the second explodes", correlation_id=corr,
        steps=[
            PlanStep(id="s1", kind=StepKind.action, capability="test.ok_revertible",
                     target={"entity": "alpha"}),
            PlanStep(id="s2", kind=StepKind.action, capability="test.boom",
                     target={"entity": "beta"}, depends_on=["s1"]),
        ],
    )
    original = get_mode(db_conn)
    set_mode(db_conn, Mode.semi_autonomous)  # auto-runs low-risk reversible actions
    try:
        insert_plan(db_conn, plan)
        done = execute_plan(plan.plan_id)
        by_id = {s.id: s for s in done.steps}
        assert done.status is PlanStatus.failed
        assert by_id["s2"].status is StepStatus.failed
        assert by_id["s1"].status is StepStatus.rolled_back  # the succeeded step was reverted
        assert reverted == ["{'entity': 'alpha'}"]  # revert() ran exactly once, on s1's target
    finally:
        set_mode(db_conn, original)
        _REGISTRY.pop("test.ok_revertible", None)
        _REGISTRY.pop("test.boom", None)
        _cleanup(db_conn, corr)
