"""container_images: per-container image baseline for deploy detection

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-29

A derived store: the current image+digest per container. Diffed each run to detect redeploys
(digest changes) → container.deployed events. Not event-sourced.
"""

from __future__ import annotations

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE container_images (
            entity     text PRIMARY KEY,
            image      text NOT NULL,
            digest     text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now()
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS container_images;")
