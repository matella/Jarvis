"""Plan persistence. Steps live embedded in the `steps` jsonb and are rewritten as the executor
updates per-step status — the plan row is the mutable projection; executions (linked by
correlation_id) are the immutable record of what actually ran."""

from __future__ import annotations

import psycopg
from psycopg.types.json import Json

from jarvis.orchestration.models import Plan


def insert_plan(conn: psycopg.Connection, plan: Plan) -> None:
    conn.execute(
        "INSERT INTO plans (plan_id, schema_version, goal, status, steps, context_ref, "
        "correlation_id, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            plan.plan_id, plan.schema_version, plan.goal, plan.status.value,
            Json([s.model_dump(mode="json") for s in plan.steps]),
            plan.context_ref, plan.correlation_id, plan.created_at,
        ),
    )


def save_steps(conn: psycopg.Connection, plan: Plan) -> None:
    """Persist the current step list + plan status (called as the executor advances)."""
    conn.execute(
        "UPDATE plans SET steps = %s, status = %s WHERE plan_id = %s",
        (Json([s.model_dump(mode="json") for s in plan.steps]), plan.status.value, plan.plan_id),
    )


def get_plan(conn: psycopg.Connection, plan_id: str) -> Plan | None:
    row = conn.execute("SELECT * FROM plans WHERE plan_id = %s", (plan_id,)).fetchone()
    return Plan(**row) if row else None


def list_plans(conn: psycopg.Connection, limit: int = 20) -> list[Plan]:
    rows = conn.execute(
        "SELECT * FROM plans ORDER BY created_at DESC LIMIT %s", (limit,)
    ).fetchall()
    return [Plan(**r) for r in rows]
