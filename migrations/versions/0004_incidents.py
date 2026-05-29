"""incidents: correlated alert clusters with an inferred root cause

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-29

A first-class operational record (schema_version + correlation_id) produced by the correlator:
deterministic clustering decides membership, the LLM supplies summary/root_cause. Links many
source alerts via event_ids[] (multi-parent → no single causation_id); context_ref enables explain.
"""

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE incidents (
            incident_id    text PRIMARY KEY,
            schema_version integer NOT NULL DEFAULT 1,
            window_label   text NOT NULL,
            severity       text NOT NULL
                           CHECK (severity IN ('debug','info','warning','error','critical')),
            summary        text NOT NULL,
            root_cause     text,
            entity_refs    text[] NOT NULL DEFAULT '{}',
            event_ids      text[] NOT NULL DEFAULT '{}',
            event_count    integer NOT NULL DEFAULT 0,
            context_ref    text,
            correlation_id text NOT NULL,
            created_at     timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX incidents_created_at_idx ON incidents (created_at);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS incidents;")
