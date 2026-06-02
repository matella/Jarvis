"""documents: markdown long-form with version history + AI co-write (user documents)

Revision ID: 0022
Revises: 0021
Create Date: 2026-06-02

Markdown-first (locked decision). The table owns the truth. Each save snapshots a `document_versions`
row (cheap append-only history; restore = set body to a chosen version). AI co-write *proposes* a new
body (one-shot inference) which the operator accepts → a normal update — the model never writes the
table directly. Research output lands here. Personal-OS module #4.
"""

from __future__ import annotations

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE documents (
            id                 text PRIMARY KEY,
            title              text NOT NULL,
            body_md            text NOT NULL DEFAULT '',
            status             text NOT NULL DEFAULT 'draft',
            source_entity_ref  text,
            schema_version     integer NOT NULL DEFAULT 1,
            created_at         timestamptz NOT NULL DEFAULT now(),
            updated_at         timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE document_versions (
            id           text PRIMARY KEY,
            document_id  text NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
            body_md      text NOT NULL,
            author       text NOT NULL DEFAULT 'operator',
            summary      text,
            created_at   timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX documents_live_idx ON documents (status, updated_at DESC);
        CREATE INDEX document_versions_doc_idx ON document_versions (document_id, created_at DESC);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS document_versions; DROP TABLE IF EXISTS documents;")
