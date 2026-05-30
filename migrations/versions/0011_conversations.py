"""conversations + messages: the chat surface (6a)

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-30

A conversation is a session with an authenticated actor; messages are its turns (role =
user|assistant|system) with optional structured artifacts. Every turn also emits a
`conversation.message` event on the spine, so the chat is replayable like everything else; this
table is the fast read model + the memory window for context assembly.
"""

from __future__ import annotations

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE conversations (
            id          text PRIMARY KEY,
            started_at  timestamptz NOT NULL DEFAULT now(),
            actor       text NOT NULL
        );
        CREATE TABLE messages (
            id              bigserial PRIMARY KEY,
            conversation_id text NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role            text NOT NULL,
            content         text NOT NULL,
            artifacts       jsonb NOT NULL DEFAULT '{}'::jsonb,
            ts              timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX messages_conversation_idx ON messages (conversation_id, id);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS messages; DROP TABLE IF EXISTS conversations;")
