"""news: cached French translation of each story (title + body)

Revision ID: 0030
Revises: 0029
Create Date: 2026-06-08

The paper presents one default language (French) with a "show original" toggle. Translating is an
extra LLM step, so the result is cached on the story keyed by `translated_hash` (a hash of the
source title+body that was translated) — the worker only re-translates when the source changes.
`title_fr`/`body_fr` empty = not yet translated (or the story is already French).
"""

from __future__ import annotations

from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE news_stories ADD COLUMN IF NOT EXISTS title_fr text NOT NULL DEFAULT '';
        ALTER TABLE news_stories ADD COLUMN IF NOT EXISTS body_fr text NOT NULL DEFAULT '';
        ALTER TABLE news_stories ADD COLUMN IF NOT EXISTS translated_hash text NOT NULL DEFAULT '';
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE news_stories DROP COLUMN IF EXISTS title_fr, "
        "DROP COLUMN IF EXISTS body_fr, DROP COLUMN IF EXISTS translated_hash;"
    )
