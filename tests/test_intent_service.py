"""Approval + mode gate unit tests — fake conn/tool/mode, no DB/Redis/infra."""

import pytest

import jarvis.intents.service as service
from jarvis.core.modes import Mode
from jarvis.intents.models import (
    Execution,
    ExecutionOutcome,
    Intent,
    IntentReasoning,
    IntentStatus,
)
from jarvis.tools.contract import Rollback, Tool


class _Conn:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return None


def _intent(**over) -> Intent:
    base = dict(
        type="docker.restart_container",
        target={"container": "probe"},
        reasoning=IntentReasoning(summary="s", confidence=0.9, risk="low", reversible=True),
        requested_by="infrastructure_agent",
        correlation_id="corr_x",
        requires_approval=True,
        status=IntentStatus.proposed,
    )
    base.update(over)
    return Intent(**base)


def _fake_tool(run_calls: list, *, fail: Exception | None = None) -> Tool:
    def run(target, *, timeout_s):
        run_calls.append(target)
        if fail:
            raise fail
        return {"restarted": target["container"]}

    return Tool(
        name="docker.restart_container", version=1, permissions=["docker:restart"],
        side_effects=True, idempotent=False, max_retries=1, timeout_seconds=5,
        rollback=Rollback.none, run=run, inspect=lambda target: {"status": "exited"},
    )


def _wire(monkeypatch, intent: Intent, mode: Mode, tool: Tool | None):
    captured: list[Execution] = []
    monkeypatch.setattr(service, "get_intent", lambda conn, iid: intent)
    monkeypatch.setattr(service, "insert_execution", lambda conn, ex: captured.append(ex))
    monkeypatch.setattr(service, "emit_event", lambda e: None)
    monkeypatch.setattr(service, "get_tool", lambda t: tool)
    monkeypatch.setattr(service, "get_mode", lambda conn: mode)
    return captured


def test_approval_required_blocks_unapproved(monkeypatch) -> None:
    intent = _intent(status=IntentStatus.proposed, requires_approval=True)
    captured = _wire(monkeypatch, intent, Mode.approval_required, _fake_tool([]))
    with pytest.raises(service.ApprovalRequired):
        service.execute(_Conn(), intent.intent_id)
    assert captured == []  # no execution row created when the gate blocks


def test_maintenance_blocks_entirely(monkeypatch) -> None:
    intent = _intent(status=IntentStatus.approved)
    captured = _wire(monkeypatch, intent, Mode.maintenance, _fake_tool([]))
    with pytest.raises(service.ModeBlocked):
        service.execute(_Conn(), intent.intent_id)
    assert captured == []


def test_observe_is_dry_run(monkeypatch) -> None:
    intent = _intent(status=IntentStatus.approved)
    run_calls: list = []
    _wire(monkeypatch, intent, Mode.observe, _fake_tool(run_calls))
    execution = service.execute(_Conn(), intent.intent_id)
    assert execution.outcome is ExecutionOutcome.skipped
    assert execution.before_state == {"status": "exited"}  # captured even in dry-run
    assert execution.after_state is None
    assert run_calls == []  # the real executor is NOT called under observe


def test_approval_required_runs_when_approved(monkeypatch) -> None:
    intent = _intent(status=IntentStatus.approved)
    run_calls: list = []
    conn = _Conn()
    _wire(monkeypatch, intent, Mode.approval_required, _fake_tool(run_calls))
    execution = service.execute(conn, intent.intent_id)
    assert execution.outcome is ExecutionOutcome.success
    assert run_calls == [{"container": "probe"}]
    assert any("UPDATE intents SET status" in sql and "executed" in str(params)
               for sql, params in conn.calls)


def test_semi_autonomous_auto_approves_and_runs_low_risk(monkeypatch) -> None:
    # low-risk + reversible + proposed (NOT approved) → semi_autonomous runs it unattended
    intent = _intent(status=IntentStatus.proposed,
                     reasoning=IntentReasoning(summary="s", confidence=0.9,
                                               risk="low", reversible=True))
    run_calls: list = []
    conn = _Conn()
    _wire(monkeypatch, intent, Mode.semi_autonomous, _fake_tool(run_calls))
    execution = service.execute(conn, intent.intent_id)
    assert execution.outcome is ExecutionOutcome.success
    assert run_calls == [{"container": "probe"}]  # ran without a human approval
    assert any("UPDATE intents SET status" in sql and "approved" in str(params)
               for sql, params in conn.calls)  # auto-approval recorded


def test_semi_autonomous_holds_high_risk_for_approval(monkeypatch) -> None:
    intent = _intent(status=IntentStatus.proposed,
                     reasoning=IntentReasoning(summary="s", confidence=0.9,
                                               risk="high", reversible=False))
    run_calls: list = []
    _wire(monkeypatch, intent, Mode.semi_autonomous, _fake_tool(run_calls))
    with pytest.raises(service.ApprovalRequired):
        service.execute(_Conn(), intent.intent_id)
    assert run_calls == []  # high-risk not auto-run


def test_executor_failure_is_typed(monkeypatch) -> None:
    import subprocess

    intent = _intent(status=IntentStatus.approved)
    tool = _fake_tool([], fail=subprocess.TimeoutExpired(cmd="docker", timeout=5))
    _wire(monkeypatch, intent, Mode.approval_required, tool)
    execution = service.execute(_Conn(), intent.intent_id)
    assert execution.outcome is ExecutionOutcome.failure
    assert execution.failure_class is not None and execution.failure_class.value == "timeout"


def test_advisory_intent_is_skipped(monkeypatch) -> None:
    intent = _intent(type="infra.recommend", requires_approval=False, status=IntentStatus.proposed)
    _wire(monkeypatch, intent, Mode.observe, None)  # no tool
    execution = service.execute(_Conn(), intent.intent_id)
    assert execution.outcome is ExecutionOutcome.skipped
    assert execution.before_state is None
