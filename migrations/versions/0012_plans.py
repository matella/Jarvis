"""plans: multi-step goals (one-shot planner → deterministic executor)

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-30

A plan is a validated DAG of known capabilities produced by ONE inference (core/planner.py); the
deterministic plan_executor walks it, each action step flowing through the existing Intent→gate→
executor. Steps live embedded in `steps` jsonb (status/outcome updated in place); executions link
back by the shared `correlation_id`, so `trace` shows the whole chain. Hard Rule 2 intact: the
model plans once, code coordinates.
"""

from __future__ import annotations

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE plans (
            plan_id        text PRIMARY KEY,
            schema_version integer NOT NULL DEFAULT 1,
            goal           text NOT NULL,
            status         text NOT NULL DEFAULT 'proposed',
            steps          jsonb NOT NULL DEFAULT '[]'::jsonb,
            context_ref    text,
            correlation_id text NOT NULL,
            created_at     timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX plans_created_at_idx ON plans (created_at);
        CREATE INDEX plans_correlation_idx ON plans (correlation_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS plans;")
