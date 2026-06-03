"""notes: freeform markdown jottings (user documents — the table owns the truth)

Revision ID: 0021
Revises: 0020
Create Date: 2026-06-02

Lighter than documents (no AI co-write/versioning), heavier than a fact. Recalled via the shared
pgvector search hook. Personal-OS module #3. Soft-delete via `archived` (kept). Awareness events
(`note.created`/`note.updated`) are notices; this table is the source of truth.
"""

from __future__ import annotations

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE notes (
            id                 text PRIMARY KEY,
            title              text NOT NULL DEFAULT '',
            body_md            text NOT NULL DEFAULT '',
            pinned             boolean NOT NULL DEFAULT false,
            archived           boolean NOT NULL DEFAULT false,
            tags               text[] NOT NULL DEFAULT '{}',
            source_entity_ref  text,
            schema_version     integer NOT NULL DEFAULT 1,
            created_at         timestamptz NOT NULL DEFAULT now(),
            updated_at         timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX notes_live_idx ON notes (archived, pinned, updated_at DESC);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS notes;")
