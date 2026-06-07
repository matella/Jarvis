"""News repository — the single write path for articles/stories + pgvector retrieval.

Idempotent ingest (ON CONFLICT canonical_hash), reactor enrichment (embedding/summary/tags/story),
clustering writes, and the read accessors both faces use (recent, top-by-coverage, vector search).
Embeddings pass as numpy float32 (the pgvector adapter); reads omit the embedding column.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import psycopg
from psycopg.types.json import Json

from jarvis.news.models import NewsArticle, NewsStory

_ART_COLS = (
    "id, source, origin_id, url, canonical_hash, lang, title, body, published_at, "
    "summary, topic, region, story_id, schema_version, recorded_at"
)
_STORY_COLS = (
    "id, lang, title, synthesized_body, claims_json, disagreements_json, "
    "source_count, origin_count, top_at, schema_version, created_at, updated_at"
)


def _vec(embedding: list[float] | None):
    return np.asarray(embedding, dtype=np.float32) if embedding else None


def _row_to_article(row: dict) -> NewsArticle:
    return NewsArticle(**row)


def _row_to_story(row: dict) -> NewsStory:
    return NewsStory(**row)


def upsert_article(conn: psycopg.Connection, art: NewsArticle) -> NewsArticle:
    """Insert the raw article; idempotent on canonical_hash (a re-post returns the existing row)."""
    art = art.with_hash()
    conn.execute(
        f"INSERT INTO news_articles ({_ART_COLS}, embedding) VALUES "
        "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (canonical_hash) DO NOTHING",
        (art.id, art.source, art.origin_id, art.url, art.canonical_hash, art.lang, art.title,
         art.body, art.published_at, art.summary, art.topic, art.region, art.story_id,
         art.schema_version, art.recorded_at, _vec(art.embedding)),
    )
    row = conn.execute(
        f"SELECT {_ART_COLS} FROM news_articles WHERE canonical_hash = %s", (art.canonical_hash,)
    ).fetchone()
    return _row_to_article(row)


def get_article(conn: psycopg.Connection, article_id: str) -> NewsArticle | None:
    row = conn.execute(
        f"SELECT {_ART_COLS} FROM news_articles WHERE id = %s", (article_id,)
    ).fetchone()
    return _row_to_article(row) if row else None


def enrich_article(conn: psycopg.Connection, article_id: str, *, embedding: list[float],
                   summary: str = "", topic: str = "", region: str = "",
                   origin_id: str | None = None, story_id: str | None = None) -> None:
    """Reactor output: store the embedding + (representative) summary/tags + cluster links."""
    conn.execute(
        "UPDATE news_articles SET embedding = %s, summary = %s, topic = %s, region = %s, "
        "origin_id = COALESCE(%s, origin_id), story_id = COALESCE(%s, story_id) WHERE id = %s",
        (_vec(embedding), summary, topic, region, origin_id, story_id, article_id),
    )


def create_story(conn: psycopg.Connection, story: NewsStory) -> NewsStory:
    conn.execute(
        f"INSERT INTO news_stories ({_STORY_COLS}, embedding) VALUES "
        "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (story.id, story.lang, story.title, story.synthesized_body, Json(story.claims_json),
         Json(story.disagreements_json), story.source_count, story.origin_count, story.top_at,
         story.schema_version, story.created_at, story.updated_at, _vec(story.embedding)),
    )
    return story


def articles_for_story(conn: psycopg.Connection, story_id: str) -> list[NewsArticle]:
    rows = conn.execute(
        f"SELECT {_ART_COLS} FROM news_articles WHERE story_id = %s "
        "ORDER BY published_at DESC NULLS LAST",
        (story_id,),
    ).fetchall()
    return [_row_to_article(r) for r in rows]


def refresh_story_counts(conn: psycopg.Connection, story_id: str) -> None:
    """Recompute distinct article + independent-origin counts (syndication collapsed)."""
    conn.execute(
        "UPDATE news_stories SET "
        "source_count = (SELECT count(*) FROM news_articles WHERE story_id = %s), "
        "origin_count = (SELECT count(DISTINCT COALESCE(origin_id, id)) FROM news_articles "
        "WHERE story_id = %s), updated_at = now() WHERE id = %s",
        (story_id, story_id, story_id),
    )


def get_story(conn: psycopg.Connection, story_id: str) -> NewsStory | None:
    row = conn.execute(
        f"SELECT {_STORY_COLS} FROM news_stories WHERE id = %s", (story_id,)
    ).fetchone()
    return _row_to_story(row) if row else None


def recent_stories(conn: psycopg.Connection, *, limit: int = 12, lang: str | None = None,
                   ) -> list[NewsStory]:
    if lang:
        rows = conn.execute(
            f"SELECT {_STORY_COLS} FROM news_stories WHERE lang = %s "
            "ORDER BY created_at DESC LIMIT %s", (lang, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT {_STORY_COLS} FROM news_stories ORDER BY created_at DESC LIMIT %s", (limit,)
        ).fetchall()
    return [_row_to_story(r) for r in rows]


def top_stories_since(conn: psycopg.Connection, since: datetime, *, limit: int = 10,
                      ) -> list[NewsStory]:
    """The day's biggest stories: most independent sources first, recency as the tiebreak."""
    rows = conn.execute(
        f"SELECT {_STORY_COLS} FROM news_stories WHERE updated_at >= %s "
        "ORDER BY origin_count DESC, updated_at DESC LIMIT %s", (since, limit),
    ).fetchall()
    return [_row_to_story(r) for r in rows]


def search_stories(conn: psycopg.Connection, query_vec: list[float], *, limit: int = 8,
                   ) -> list[NewsStory]:
    """Semantic search over stories (cosine). Empty query vector → recent."""
    if not query_vec:
        return recent_stories(conn, limit=limit)
    rows = conn.execute(
        f"SELECT {_STORY_COLS} FROM news_stories WHERE embedding IS NOT NULL "
        "ORDER BY embedding <=> %s LIMIT %s", (_vec(query_vec), limit),
    ).fetchall()
    return [_row_to_story(r) for r in rows]


def set_synthesis(conn: psycopg.Connection, story_id: str, *, title: str, body: str,
                  claims: list[dict], disagreements: list[dict]) -> None:
    conn.execute(
        "UPDATE news_stories SET title = %s, synthesized_body = %s, claims_json = %s, "
        "disagreements_json = %s, top_at = now(), updated_at = now() WHERE id = %s",
        (title, body, Json(claims), Json(disagreements), story_id),
    )
