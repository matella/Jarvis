"""routines: scheduled proactive briefings (cron-ish over existing capabilities)

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-30

A routine is a named schedule + an action spec that composes existing capabilities (summary /
briefing / search). A daemon worker fires due routines (change-aware via last_run, never a naive
timer; suspended under maintenance) → a `routine.completed` event + optional notification. Makes
Jarvis proactive without any new reasoning path — it reuses the gated, observable spine.
"""

from __future__ import annotations

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE routines (
            id          text PRIMARY KEY,
            name        text NOT NULL,
            schedule    jsonb NOT NULL,
            action      jsonb NOT NULL,
            enabled     boolean NOT NULL DEFAULT true,
            last_run    timestamptz,
            created_at  timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX routines_enabled_idx ON routines (enabled);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS routines;")
