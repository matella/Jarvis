"""user_facts: durable operator facts injected into the agent's context

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-30

Small key→value facts about the operator/home (city, timezone, preferences) that should be
recalled on EVERY turn, not retrieved by similarity. Distinct from `memory` (semantic, embedded,
similarity-retrieved): a fact is always-on context. Upserted by (scope, key) so "my city is X"
updates rather than accretes. `scope` is 'global' today (single operator) but leaves room for
per-actor facts later.
"""

from __future__ import annotations

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE user_facts (
            scope          text NOT NULL DEFAULT 'global',
            key            text NOT NULL,
            value          text NOT NULL,
            schema_version integer NOT NULL DEFAULT 1,
            updated_at     timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (scope, key)
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_facts;")
