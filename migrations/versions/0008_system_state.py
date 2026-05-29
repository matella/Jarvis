"""system_state: small key/value store for runtime-settable system state (operational mode)

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-29

Holds the live operational mode (key='mode') so it can be changed at runtime (`jarvis mode set`)
and picked up by the daemon/gate without a restart. Not event-sourced — it's current settings.
"""

from __future__ import annotations

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE system_state (
            key        text PRIMARY KEY,
            value      text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now()
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS system_state;")
