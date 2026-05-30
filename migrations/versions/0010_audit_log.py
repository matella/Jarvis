"""audit_log: who did what (human/agent actions) — attributable + queryable

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-30

Every action (approve/reject/execute/mode-change/...) records an audit row with an actor. Actor
is coarse now (cli/reactor/system); real user identities arrive with gateway auth (6a) and slot
into the same column.
"""

from __future__ import annotations

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE audit_log (
            id      bigserial PRIMARY KEY,
            ts      timestamptz NOT NULL DEFAULT now(),
            actor   text NOT NULL,
            action  text NOT NULL,
            target  text,
            details jsonb NOT NULL DEFAULT '{}'::jsonb
        );
        CREATE INDEX audit_log_ts_idx ON audit_log (ts);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_log;")
