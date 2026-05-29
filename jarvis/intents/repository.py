"""Intent + Execution persistence — thin SQL over psycopg3. Caller owns the transaction."""

from __future__ import annotations

import psycopg
from psycopg.types.json import Json

from jarvis.intents.models import Execution, Intent

_INTENT_COLUMNS = (
    "intent_id, schema_version, type, target, reasoning, requested_by, context_ref, "
    "requires_approval, status, created_at, correlation_id, causation_id"
)
_EXECUTION_COLUMNS = (
    "exec_id, schema_version, intent_id, attempt, outcome, before_state, after_state, "
    "error, failure_class, created_at, correlation_id, causation_id"
)


def insert_intent(conn: psycopg.Connection, intent: Intent) -> None:
    conn.execute(
        f"INSERT INTO intents ({_INTENT_COLUMNS}) VALUES "
        "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            intent.intent_id,
            intent.schema_version,
            intent.type,
            Json(intent.target),
            Json(intent.reasoning.model_dump()),
            intent.requested_by,
            intent.context_ref,
            intent.requires_approval,
            intent.status.value,
            intent.created_at,
            intent.correlation_id,
            intent.causation_id,
        ),
    )


def get_intent(conn: psycopg.Connection, intent_id: str) -> Intent | None:
    row = conn.execute(
        "SELECT * FROM intents WHERE intent_id = %s", (intent_id,)
    ).fetchone()
    return Intent(**row) if row else None


def insert_execution(conn: psycopg.Connection, execution: Execution) -> None:
    conn.execute(
        f"INSERT INTO executions ({_EXECUTION_COLUMNS}) VALUES "
        "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            execution.exec_id,
            execution.schema_version,
            execution.intent_id,
            execution.attempt,
            execution.outcome.value,
            Json(execution.before_state) if execution.before_state is not None else None,
            Json(execution.after_state) if execution.after_state is not None else None,
            execution.error,
            execution.failure_class.value if execution.failure_class is not None else None,
            execution.created_at,
            execution.correlation_id,
            execution.causation_id,
        ),
    )


def get_executions_for_intent(
    conn: psycopg.Connection, intent_id: str
) -> list[Execution]:
    rows = conn.execute(
        "SELECT * FROM executions WHERE intent_id = %s ORDER BY exec_id",
        (intent_id,),
    ).fetchall()
    return [Execution(**row) for row in rows]
