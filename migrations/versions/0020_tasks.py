"""tasks: the to-do module (user documents — the table owns the truth)

Revision ID: 0020
Revises: 0019
Create Date: 2026-06-02

Richer than reminders (which stay the time-based nudge): a task has status/priority/subtasks and a
`source_entity_ref` linking provenance ("from email:<id>"). Personal-OS module #2. Soft-delete via
status='dropped' (kept for audit). Awareness events (`task.created`/`task.completed`) are notices;
this table is the source of truth.
"""

from __future__ import annotations

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE tasks (
            id                 text PRIMARY KEY,
            title              text NOT NULL,
            notes              text NOT NULL DEFAULT '',
            status             text NOT NULL DEFAULT 'open',
            priority           text NOT NULL DEFAULT 'normal',
            due_at             timestamptz,
            completed_at       timestamptz,
            parent_id          text REFERENCES tasks (id) ON DELETE SET NULL,
            source_entity_ref  text,
            schema_version     integer NOT NULL DEFAULT 1,
            created_at         timestamptz NOT NULL DEFAULT now(),
            updated_at         timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX tasks_status_idx ON tasks (status, due_at);
        CREATE INDEX tasks_due_idx ON tasks (due_at) WHERE status IN ('open', 'doing');
        CREATE INDEX tasks_parent_idx ON tasks (parent_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tasks;")
