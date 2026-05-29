"""contexts: stored assembled context (prompt + model/params) keyed by context_ref

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-29

The provenance store behind `jarvis explain`/`replay`: the exact assembled context and model
params that produced an intent. Insert is idempotent (a reused context_ref dedups).
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE contexts (
            context_ref text PRIMARY KEY,
            prompt      text NOT NULL,
            model       text NOT NULL,
            params      jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at  timestamptz NOT NULL DEFAULT now()
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS contexts;")
