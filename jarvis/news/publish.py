"""Publish the finished news read-model into the standalone world-news database.

Jarvis owns the engine (scrape/pool/AI) in jarvis-postgres; this copies the presentable stories into
the world-news app's OWN Postgres so that site is independent (it serves from its own DB even if the
Jarvis app is down). One-way publish (Jarvis → site DB), idempotent upsert on story id. No-op unless
`world_news_db_url` is set.
"""

from __future__ import annotations

import psycopg
from psycopg.types.json import Json

from jarvis.config import get_settings
from jarvis.db import connect as jarvis_connect
from jarvis.news import repository as repo

_DDL = """
CREATE TABLE IF NOT EXISTS published_stories (
    id                 text PRIMARY KEY,
    lang               text NOT NULL DEFAULT 'en',
    title              text NOT NULL DEFAULT '',
    body               text NOT NULL DEFAULT '',
    claims_json        jsonb NOT NULL DEFAULT '[]'::jsonb,
    disagreements_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    source_count       integer NOT NULL DEFAULT 0,
    origin_count       integer NOT NULL DEFAULT 0,
    updated_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS published_stories_recent_idx ON published_stories (updated_at DESC);
"""

_UPSERT = """
INSERT INTO published_stories
    (id, lang, title, body, claims_json, disagreements_json, source_count, origin_count, updated_at)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s, now())
ON CONFLICT (id) DO UPDATE SET
    title=EXCLUDED.title, body=EXCLUDED.body, claims_json=EXCLUDED.claims_json,
    disagreements_json=EXCLUDED.disagreements_json, source_count=EXCLUDED.source_count,
    origin_count=EXCLUDED.origin_count, updated_at=now();
"""


def publish_stories(limit: int = 80) -> int:
    """Upsert the most recent stories into the world-news DB. Returns the count published."""
    url = get_settings().world_news_db_url
    if not url:
        return 0
    with jarvis_connect() as jc:
        repo.prune_empty_stories(jc)  # drop orphan stories before publishing the read-model
        jc.commit()
        stories = repo.recent_stories(jc, limit=limit)
    if not stories:
        return 0
    with psycopg.connect(url) as sc:
        sc.execute(_DDL)
        for s in stories:
            sc.execute(_UPSERT, (s.id, s.lang, s.title, s.synthesized_body,
                                 Json(s.claims_json), Json(s.disagreements_json),
                                 s.source_count, s.origin_count))
        # Reconcile: the read-model is exactly the current set — drop anything no longer published
        # (e.g. stories from a prior rebuild) so the site never shows stale editions.
        sc.execute("DELETE FROM published_stories WHERE id <> ALL(%s)", ([s.id for s in stories],))
        sc.commit()
    return len(stories)
