"""news: cached French translation of a story's "where sources disagree" panel

Revision ID: 0031
Revises: 0030
Create Date: 2026-06-08

The disagreements panel is structured synthesis output (point + positions), generated in the story's
source language. The paper shows it by default in French, so it's translated + cached alongside
title_fr/body_fr (cleared by set_synthesis, like the other translations).
"""

from __future__ import annotations

from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE news_stories ADD COLUMN IF NOT EXISTS "
        "disagreements_fr jsonb NOT NULL DEFAULT '[]'::jsonb;"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE news_stories DROP COLUMN IF EXISTS disagreements_fr;")
