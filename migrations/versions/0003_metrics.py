"""metrics: raw resource-telemetry time-series (container + GPU samples)

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-29

Deliberately NOT an event-sourced/boundary record (no schema_version / causal ids, like
state/snapshots): it's high-volume telemetry written directly by the poller. Only debounced
threshold *signal events* reach the event log. bigserial PK fits the time-series access pattern.
"""

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE metrics (
            id     bigserial PRIMARY KEY,
            entity text NOT NULL,
            kind   text NOT NULL CHECK (kind IN ('container', 'gpu')),
            sample jsonb NOT NULL,
            ts     timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX metrics_entity_ts_idx ON metrics (entity, ts DESC);
        CREATE INDEX metrics_ts_idx        ON metrics (ts);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS metrics;")
