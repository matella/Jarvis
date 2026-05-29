"""playbooks: operator-authored procedural memory (retrieved to ground agent proposals)

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-29

Procedural memory (ARCHITECTURE 8.3) in pgvector: title + when_to_use + procedure + embedding,
retrieved by similarity to a situation.
"""

from __future__ import annotations

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE playbooks (
            id          text PRIMARY KEY,
            title       text NOT NULL,
            when_to_use text NOT NULL DEFAULT '',
            procedure   text NOT NULL,
            embedding   vector(768) NOT NULL,
            created_at  timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX playbooks_embedding_idx ON playbooks USING hnsw (embedding vector_cosine_ops);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS playbooks;")
