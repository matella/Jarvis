"""deferrals: reasoning queued while the LLM is unreachable (graceful degradation)

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-30

When inference is down, the deterministic plumbing (ingest → events → projector → notify) keeps
running; reasoning steps that can't run are *deferred* here instead of crashing a worker. A drain
worker replays them once the model is back. Degrade, don't crash.
"""

from __future__ import annotations

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE deferrals (
            id          text PRIMARY KEY,
            kind        text NOT NULL,
            payload     jsonb NOT NULL DEFAULT '{}'::jsonb,
            attempts    integer NOT NULL DEFAULT 0,
            created_at  timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX deferrals_kind_idx ON deferrals (kind);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS deferrals;")
