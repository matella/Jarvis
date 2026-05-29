"""code_chunks: embedded code/config excerpts for retrieval-augmented code Q&A

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-29

A derived store (like metrics/topology/memory): chunks of indexed repo files + embeddings.
Re-index replaces a repo's chunks. Secrets are excluded/redacted upstream — never stored here.
"""

from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE code_chunks (
            id         text PRIMARY KEY,
            repo       text NOT NULL,
            path       text NOT NULL,
            start_line integer NOT NULL,
            end_line   integer NOT NULL,
            content    text NOT NULL,
            embedding  vector(768) NOT NULL,
            indexed_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX code_chunks_repo_idx      ON code_chunks (repo);
        CREATE INDEX code_chunks_embedding_idx ON code_chunks USING hnsw (embedding vector_cosine_ops);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS code_chunks;")
