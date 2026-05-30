"""reminders: time-based nudges the operator sets, fired via the notifier

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-30

Self-contained (no external service): "remind me to call the dentist tomorrow at 9" → a row here;
a worker fires due, unfired reminders through the notification channel. Append-only-ish: a fired
reminder is marked, not deleted, so it stays auditable.
"""

from __future__ import annotations

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE reminders (
            id             text PRIMARY KEY,
            text           text NOT NULL,
            due_at         timestamptz NOT NULL,
            fired          boolean NOT NULL DEFAULT false,
            schema_version integer NOT NULL DEFAULT 1,
            created_at     timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX reminders_due_idx ON reminders (fired, due_at);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS reminders;")
