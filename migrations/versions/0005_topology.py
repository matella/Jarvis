"""topology: deterministic service-dependency edges derived from docker inspect

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-29

A derived store (like metrics): built by inspecting containers, not from the event log, so no
schema_version/causal ids. Current-snapshot semantics — each build rewrites the edge set.
"""

from __future__ import annotations

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE topology (
            src_entity text NOT NULL,
            dst_entity text NOT NULL,
            relation   text NOT NULL
                       CHECK (relation IN ('depends_on', 'network_mode', 'same_project')),
            attrs      jsonb NOT NULL DEFAULT '{}'::jsonb,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (src_entity, dst_entity, relation)
        );
        CREATE INDEX topology_src_idx ON topology (src_entity);
        CREATE INDEX topology_dst_idx ON topology (dst_entity);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS topology;")
