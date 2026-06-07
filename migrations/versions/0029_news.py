"""news: scraped articles + pooled stories (multilingual, pgvector)

Revision ID: 0029
Revises: 0028
Create Date: 2026-06-07

The news module's truth tables. `news_articles` are raw scraped items (deduped on canonical_hash,
syndication-collapsed via origin_id); `news_stories` are pooled clusters with the tier-B synthesis.
Embeddings are vector(1024) — bge-m3 multilingual, distinct from the nomic(768) search index — so
FR/NL clustering/search is good without migrating the global embedding dimension.
"""

from __future__ import annotations

from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE news_stories (
            id                 text PRIMARY KEY,
            lang               text NOT NULL DEFAULT 'en',
            title              text NOT NULL DEFAULT '',
            synthesized_body   text NOT NULL DEFAULT '',
            claims_json        jsonb NOT NULL DEFAULT '[]'::jsonb,
            disagreements_json jsonb NOT NULL DEFAULT '[]'::jsonb,
            source_count       integer NOT NULL DEFAULT 0,
            origin_count       integer NOT NULL DEFAULT 0,
            top_at             timestamptz,
            embedding          vector(1024),
            schema_version     integer NOT NULL DEFAULT 1,
            created_at         timestamptz NOT NULL DEFAULT now(),
            updated_at         timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX news_stories_recent_idx ON news_stories (lang, created_at DESC);
        CREATE INDEX news_stories_embedding_idx
            ON news_stories USING hnsw (embedding vector_cosine_ops);

        CREATE TABLE news_articles (
            id              text PRIMARY KEY,
            source          text NOT NULL,
            origin_id       text,
            url             text NOT NULL DEFAULT '',
            canonical_hash  text NOT NULL UNIQUE,
            lang            text NOT NULL DEFAULT 'en',
            title           text NOT NULL DEFAULT '',
            body            text NOT NULL DEFAULT '',
            published_at    timestamptz,
            summary         text NOT NULL DEFAULT '',
            topic           text NOT NULL DEFAULT '',
            region          text NOT NULL DEFAULT '',
            embedding       vector(1024),
            story_id        text REFERENCES news_stories(id) ON DELETE SET NULL,
            schema_version  integer NOT NULL DEFAULT 1,
            recorded_at     timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX news_articles_story_idx ON news_articles (story_id);
        CREATE INDEX news_articles_recent_idx ON news_articles (lang, published_at DESC);
        CREATE INDEX news_articles_embedding_idx
            ON news_articles USING hnsw (embedding vector_cosine_ops);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS news_articles; DROP TABLE IF EXISTS news_stories;")
