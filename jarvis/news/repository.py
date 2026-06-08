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
    "source_count, origin_count, top_at, schema_version, created_at, updated_at, "
    "title_fr, body_fr, translated_hash, disagreements_fr"
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


def pending_article_ids(conn: psycopg.Connection, *, limit: int = 20) -> list[str]:
    """Articles stored but not yet enriched (embedding IS NULL) — the processing backlog, oldest
    first. Bounded so the worker drains at GPU/CPU pace (backpressure) without blocking ingest."""
    rows = conn.execute(
        "SELECT id FROM news_articles WHERE embedding IS NULL "
        "ORDER BY recorded_at LIMIT %s", (limit,),
    ).fetchall()
    return [r["id"] for r in rows]


def get_article(conn: psycopg.Connection, article_id: str) -> NewsArticle | None:
    row = conn.execute(
        f"SELECT {_ART_COLS} FROM news_articles WHERE id = %s", (article_id,)
    ).fetchone()
    return _row_to_article(row) if row else None


def get_by_hash_id(conn: psycopg.Connection, canonical_hash: str) -> str | None:
    """The id of an already-stored article with this hash, or None — the dedup check for ingest."""
    row = conn.execute(
        "SELECT id FROM news_articles WHERE canonical_hash = %s", (canonical_hash,)
    ).fetchone()
    return row["id"] if row else None


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
        "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (story.id, story.lang, story.title, story.synthesized_body, Json(story.claims_json),
         Json(story.disagreements_json), story.source_count, story.origin_count, story.top_at,
         story.schema_version, story.created_at, story.updated_at,
         story.title_fr, story.body_fr, story.translated_hash,
         Json(story.disagreements_fr), _vec(story.embedding)),
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


def story_topics(conn: psycopg.Connection, story_ids: list[str]) -> dict[str, str]:
    """One representative topic per story (tier-A tag on its articles) → {story_id: topic}."""
    if not story_ids:
        return {}
    rows = conn.execute(
        "SELECT DISTINCT ON (story_id) story_id, topic FROM news_articles "
        "WHERE story_id = ANY(%s) AND topic <> '' ORDER BY story_id, recorded_at",
        (story_ids,),
    ).fetchall()
    return {r["story_id"]: r["topic"] for r in rows}


def story_summaries(conn: psycopg.Connection, story_ids: list[str]) -> dict[str, str]:
    """The representative tier-A summary per story → {story_id: summary}. The fallback body shown
    before (or instead of) a full tier-B synthesis, so every story always has content."""
    if not story_ids:
        return {}
    rows = conn.execute(
        "SELECT DISTINCT ON (story_id) story_id, summary FROM news_articles "
        "WHERE story_id = ANY(%s) AND summary <> '' ORDER BY story_id, recorded_at",
        (story_ids,),
    ).fetchall()
    return {r["story_id"]: r["summary"] for r in rows}


def stories_awaiting_synthesis(conn: psycopg.Connection, *, limit: int = 3) -> list[NewsStory]:
    """Multi-source stories that don't yet have a full synthesis — the tier-B work queue,
    newest first. (Single-source stories stay on their tier-A summary; synthesis adds no value.)"""
    rows = conn.execute(
        f"SELECT {_STORY_COLS} FROM news_stories WHERE source_count > 1 "
        "AND synthesized_body = '' ORDER BY origin_count DESC, updated_at DESC LIMIT %s",
        (limit,),
    ).fetchall()
    return [_row_to_story(r) for r in rows]


def untranslated_stories(conn: psycopg.Connection, *, default_lang: str = "fr",
                         limit: int = 8) -> list[NewsStory]:
    """Non-default-language stories that still need a French translation (title_fr empty), most-
    covered first then most-recent — so the headline/lead and multi-source stories (what the reader
    actually sees) translate before the long tail. `set_synthesis` clears title_fr, so a freshly-
    synthesised story re-enters this queue and re-translates."""
    rows = conn.execute(
        f"SELECT {_STORY_COLS} FROM news_stories WHERE lang <> %s AND title_fr = '' "
        "ORDER BY origin_count DESC, created_at DESC LIMIT %s", (default_lang, limit),
    ).fetchall()
    return [_row_to_story(r) for r in rows]


def set_translation(conn: psycopg.Connection, story_id: str, *, title_fr: str, body_fr: str,
                    h: str, disagreements_fr: list[dict] | None = None) -> None:
    conn.execute(
        "UPDATE news_stories SET title_fr = %s, body_fr = %s, translated_hash = %s, "
        "disagreements_fr = %s WHERE id = %s",
        (title_fr, body_fr, h, Json(disagreements_fr or []), story_id),
    )


def story_sources(conn: psycopg.Connection, story_ids: list[str]) -> dict[str, list[dict]]:
    """Per story, the distinct source outlets + a URL to each original article (for 'view source'
    links) → {story_id: [{"name", "url"}]}. One row per independent origin, newest first."""
    if not story_ids:
        return {}
    rows = conn.execute(
        "SELECT DISTINCT ON (story_id, COALESCE(origin_id, id)) story_id, source, url "
        "FROM news_articles WHERE story_id = ANY(%s) AND url <> '' "
        "ORDER BY story_id, COALESCE(origin_id, id), recorded_at DESC",
        (story_ids,),
    ).fetchall()
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["story_id"], []).append({"name": r["source"], "url": r["url"]})
    return out


def story_threads(conn: psycopg.Connection, story_ids: list[str], *, k: int = 6,
                  max_distance: float = 0.42, window_days: int = 30) -> dict[str, list[str]]:
    """For each story, its most-similar OTHER stories within the window — the 'subject thread' that
    lets the reader follow how a subject evolved across days. {story_id: [related_id, ...]}, nearest
    first. Pure pgvector (cosine `<=>`) over the embeddings we already store — no model calls.
    `max_distance` is conservative (≈0.42) to avoid threading unrelated stories; tune as needed."""
    if not story_ids:
        return {}
    rows = conn.execute(
        "SELECT s.id AS sid, r.id AS rid FROM news_stories s "
        "CROSS JOIN LATERAL ("
        "  SELECT cand.id, s.embedding <=> cand.embedding AS d FROM news_stories cand "
        "  WHERE cand.id <> s.id AND cand.embedding IS NOT NULL "
        "    AND cand.created_at > now() - make_interval(days => %s) "
        "    AND s.embedding <=> cand.embedding < %s "
        "  ORDER BY s.embedding <=> cand.embedding LIMIT %s"
        ") AS r WHERE s.id = ANY(%s) AND s.embedding IS NOT NULL",
        (window_days, max_distance, k, story_ids),
    ).fetchall()
    out: dict[str, list[str]] = {}
    for r in rows:
        out.setdefault(r["sid"], []).append(r["rid"])
    return out


def synthesis_counts(conn: psycopg.Connection) -> dict[str, int]:
    """How many stories are fully synthesised vs awaiting it (multi-source, no body)."""
    done = conn.execute(
        "SELECT count(*) n FROM news_stories WHERE synthesized_body <> ''").fetchone()["n"]
    awaiting = conn.execute(
        "SELECT count(*) n FROM news_stories WHERE source_count > 1 "
        "AND synthesized_body = ''").fetchone()["n"]
    return {"synthesized": done, "awaiting_synthesis": awaiting}


def prune_empty_stories(conn: psycopg.Connection) -> int:
    """Delete stories with no articles attached — orphans (e.g. from a race) and retention debris.
    Returns rows removed. Safe hygiene; the real stories always have at least their seed article."""
    return conn.execute(
        "DELETE FROM news_stories WHERE id NOT IN "
        "(SELECT story_id FROM news_articles WHERE story_id IS NOT NULL)"
    ).rowcount


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


def nearest_story(conn: psycopg.Connection, query_vec: list[float], *, lang: str,
                  window_h: int = 48, max_distance: float = 0.18) -> str | None:
    """The closest same-language story within the time window, if within `max_distance` (cosine).

    `max_distance` = 1 − sim_threshold (pgvector `<=>` is cosine distance). None → new story.
    """
    if not query_vec:
        return None
    row = conn.execute(
        "SELECT id, embedding <=> %s AS d FROM news_stories "
        "WHERE lang = %s AND embedding IS NOT NULL "
        "AND created_at >= now() - make_interval(hours => %s) "
        "ORDER BY embedding <=> %s LIMIT 1",
        (_vec(query_vec), lang, window_h, _vec(query_vec)),
    ).fetchone()
    if row and float(row["d"]) <= max_distance:
        return row["id"]
    return None


def attach_story_embedding(conn: psycopg.Connection, story_id: str, embedding: list[float]) -> None:
    conn.execute("UPDATE news_stories SET embedding = %s WHERE id = %s",
                 (_vec(embedding), story_id))


def set_synthesis(conn: psycopg.Connection, story_id: str, *, title: str, body: str,
                  claims: list[dict], disagreements: list[dict]) -> None:
    conn.execute(
        # Reset the cached translation: the body just changed, so it must be re-translated (the
        # story re-enters untranslated_stories).
        "UPDATE news_stories SET title = %s, synthesized_body = %s, claims_json = %s, "
        "disagreements_json = %s, title_fr = '', body_fr = '', translated_hash = '', "
        "disagreements_fr = '[]'::jsonb, top_at = now(), updated_at = now() WHERE id = %s",
        (title, body, Json(claims), Json(disagreements), story_id),
    )
