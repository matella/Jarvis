"""recipes: notes-flavored recipes + URL→structured import (user documents)

Revision ID: 0023
Revises: 0026
Create Date: 2026-06-02

The table owns the truth. Import = egress-guarded fetch → ONE grammar inference → structured recipe.
Cross-module payoff: recipe → shopping list → tasks. Personal-OS module #6.
"""

from __future__ import annotations

from alembic import op

revision = "0023"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE recipes (
            id               text PRIMARY KEY,
            title            text NOT NULL,
            source_url       text,
            servings         integer,
            ingredients_json jsonb NOT NULL DEFAULT '[]'::jsonb,
            steps_json       jsonb NOT NULL DEFAULT '[]'::jsonb,
            tags             text[] NOT NULL DEFAULT '{}',
            notes_md         text NOT NULL DEFAULT '',
            archived         boolean NOT NULL DEFAULT false,
            schema_version   integer NOT NULL DEFAULT 1,
            created_at       timestamptz NOT NULL DEFAULT now(),
            updated_at       timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX recipes_live_idx ON recipes (archived, updated_at DESC);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS recipes;")
