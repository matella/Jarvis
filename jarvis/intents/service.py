"""Intent lifecycle service — the approval + mode gate, and the only path to execution.

`LLM → Intent` already happened (the agent). This is the deterministic tail:
`Intent → approval gate → mode gate → capability-scoped executor → Execution`. Under the
default `observe` mode every approved action is a **dry-run** (records a skipped execution,
captures before_state, touches no infrastructure); a non-observe mode runs the real executor.
"""

from __future__ import annotations

import subprocess

import psycopg

from jarvis.config import get_settings
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import emit_event
from jarvis.intents.models import (
    Execution,
    ExecutionOutcome,
    FailureClass,
    Intent,
    IntentStatus,
)
from jarvis.intents.repository import get_intent, insert_execution
from jarvis.tools.registry import get_tool

OBSERVE = "observe"


class IntentNotFound(Exception):
    pass


class ApprovalRequired(Exception):
    """Raised when execution is attempted on an intent that still needs approval."""


def _set_status(conn: psycopg.Connection, intent_id: str, status: IntentStatus) -> None:
    conn.execute(
        "UPDATE intents SET status = %s WHERE intent_id = %s", (status.value, intent_id)
    )


def _require(conn: psycopg.Connection, intent_id: str) -> Intent:
    intent = get_intent(conn, intent_id)
    if intent is None:
        raise IntentNotFound(intent_id)
    return intent


def approve(conn: psycopg.Connection, intent_id: str) -> Intent:
    intent = _require(conn, intent_id)
    _set_status(conn, intent_id, IntentStatus.approved)
    emit_event(_intent_event("intent.approved", intent))
    return _require(conn, intent_id)


def reject(conn: psycopg.Connection, intent_id: str) -> Intent:
    _require(conn, intent_id)
    _set_status(conn, intent_id, IntentStatus.rejected)
    return _require(conn, intent_id)


def execute(conn: psycopg.Connection, intent_id: str) -> Execution:
    intent = _require(conn, intent_id)
    if intent.requires_approval and intent.status is not IntentStatus.approved:
        raise ApprovalRequired(
            f"intent {intent_id} requires approval (status={intent.status.value})"
        )

    settings = get_settings()
    tool = get_tool(intent.type)
    before: dict | None = None
    after: dict | None = None
    error: str | None = None
    failure_class: FailureClass | None = None

    if tool is None:
        outcome = ExecutionOutcome.skipped  # advisory intent — nothing to execute
    else:
        if tool.inspect is not None:
            try:
                before = tool.inspect(intent.target)
            except Exception as exc:  # noqa: BLE001 — before-state is best-effort
                error = f"inspect failed: {exc}"
        if settings.jarvis_mode == OBSERVE:
            outcome = ExecutionOutcome.skipped  # dry-run — propose-only, no infra touched
        else:
            outcome, after, error, failure_class = _run_tool(tool, intent, error)

    execution = Execution(
        intent_id=intent.intent_id,
        outcome=outcome,
        before_state=before,
        after_state=after,
        error=error,
        failure_class=failure_class,
        correlation_id=intent.correlation_id,
        causation_id=intent.intent_id,
    )
    insert_execution(conn, execution)

    if outcome is ExecutionOutcome.success:
        _set_status(conn, intent_id, IntentStatus.executed)
    elif outcome is ExecutionOutcome.failure:
        _set_status(conn, intent_id, IntentStatus.failed)

    emit_event(
        _intent_event(
            "execution.recorded", intent,
            severity=Severity.warning if outcome is ExecutionOutcome.failure else Severity.info,
            outcome=outcome.value,
            failure_class=failure_class.value if failure_class else None,
            mode=settings.jarvis_mode,
            exec_id=execution.exec_id,
        )
    )
    return execution


def _run_tool(tool, intent: Intent, error: str | None):
    try:
        tool.run(intent.target, timeout_s=tool.timeout_seconds)
        after = tool.inspect(intent.target) if tool.inspect is not None else None
        return ExecutionOutcome.success, after, error, None
    except subprocess.TimeoutExpired as exc:
        return ExecutionOutcome.failure, None, str(exc), FailureClass.timeout
    except subprocess.CalledProcessError as exc:
        return ExecutionOutcome.failure, None, (exc.stderr or str(exc)), FailureClass.unknown
    except ValueError as exc:  # invalid target rejected by the capability
        return ExecutionOutcome.failure, None, str(exc), FailureClass.validation_failure
    except Exception as exc:  # noqa: BLE001
        return ExecutionOutcome.failure, None, str(exc), FailureClass.unknown


def _intent_event(
    event_type: str, intent: Intent, *, severity: Severity = Severity.info, **payload: object
) -> Event:
    return Event(
        type=event_type,
        severity=severity,
        source="orchestrator",
        entity_ref=f"intent:{intent.intent_id}",
        occurred_at=utcnow(),
        payload=payload,
        correlation_id=intent.correlation_id,
        causation_id=intent.intent_id,
    )
