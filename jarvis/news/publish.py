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
    topic              text NOT NULL DEFAULT '',
    claims_json        jsonb NOT NULL DEFAULT '[]'::jsonb,
    disagreements_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    source_count       integer NOT NULL DEFAULT 0,
    origin_count       integer NOT NULL DEFAULT 0,
    synthesized        boolean NOT NULL DEFAULT false,
    title_fr           text NOT NULL DEFAULT '',
    body_fr            text NOT NULL DEFAULT '',
    sources_json       jsonb NOT NULL DEFAULT '[]'::jsonb,
    updated_at         timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE published_stories ADD COLUMN IF NOT EXISTS topic text NOT NULL DEFAULT '';
ALTER TABLE published_stories ADD COLUMN IF NOT EXISTS synthesized boolean NOT NULL DEFAULT false;
ALTER TABLE published_stories ADD COLUMN IF NOT EXISTS title_fr text NOT NULL DEFAULT '';
ALTER TABLE published_stories ADD COLUMN IF NOT EXISTS body_fr text NOT NULL DEFAULT '';
ALTER TABLE published_stories ADD COLUMN IF NOT EXISTS sources_json jsonb
    NOT NULL DEFAULT '[]'::jsonb;
CREATE INDEX IF NOT EXISTS published_stories_recent_idx ON published_stories (updated_at DESC);
"""

_UPSERT = """
INSERT INTO published_stories
    (id, lang, title, body, title_fr, body_fr, topic, claims_json, disagreements_json,
     source_count, origin_count, synthesized, sources_json, updated_at)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
ON CONFLICT (id) DO UPDATE SET
    title=EXCLUDED.title, body=EXCLUDED.body, title_fr=EXCLUDED.title_fr, body_fr=EXCLUDED.body_fr,
    topic=EXCLUDED.topic, claims_json=EXCLUDED.claims_json,
    disagreements_json=EXCLUDED.disagreements_json, source_count=EXCLUDED.source_count,
    origin_count=EXCLUDED.origin_count, synthesized=EXCLUDED.synthesized,
    sources_json=EXCLUDED.sources_json, updated_at=now();
"""


_STATUS_DDL = """
CREATE TABLE IF NOT EXISTS news_status (
    id integer PRIMARY KEY DEFAULT 1,
    stats jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT now()
);
"""
_STATUS_UPSERT = (
    "INSERT INTO news_status (id, stats, updated_at) VALUES (1, %s, now()) "
    "ON CONFLICT (id) DO UPDATE SET stats=EXCLUDED.stats, updated_at=now();"
)


def _status_snapshot(jc: psycopg.Connection) -> dict:
    """Pipeline health for the admin dashboard — computed against Jarvis's own news tables, incl.
    processing/synthesis ETAs so the operator has full knowledge of what's running."""
    one = lambda sql: jc.execute(sql).fetchone()["n"]  # noqa: E731
    by_lang = {r["lang"]: r["n"]
               for r in jc.execute("SELECT lang, count(*) n FROM news_articles "
                                    "GROUP BY lang ORDER BY n DESC").fetchall()}
    last = jc.execute("SELECT max(recorded_at) m FROM news_articles").fetchone()["m"]
    pending = one("SELECT count(*) n FROM news_articles WHERE embedding IS NULL")
    syn = repo.synthesis_counts(jc)
    s = get_settings()
    # ETAs from worker cadences: process = 20/interval; synthesis = ~3/interval.
    proc_cycles = pending / 20
    synth_cycles = syn["awaiting_synthesis"] / 3
    process_eta_min = round(proc_cycles * s.news_process_interval_s / 60, 1) if pending else 0
    synth_eta_min = (round(synth_cycles * s.news_synthesize_interval_s / 60, 1)
                     if syn["awaiting_synthesis"] else 0)
    dl = s.news_default_lang
    awaiting_tr = one(f"SELECT count(*) n FROM news_stories WHERE lang <> '{dl}' AND title_fr = ''")
    return {
        "articles": one("SELECT count(*) n FROM news_articles"),
        "pending": pending,
        "stories": one("SELECT count(*) n FROM news_stories"),
        "multi_source": one("SELECT count(*) n FROM news_stories WHERE source_count > 1"),
        "synthesized": syn["synthesized"],
        "awaiting_synthesis": syn["awaiting_synthesis"],
        "translated": one(f"SELECT count(*) n FROM news_stories WHERE lang <> '{dl}' "
                          "AND title_fr <> ''"),
        "awaiting_translation": awaiting_tr,
        "default_lang": dl,
        "process_eta_min": process_eta_min,
        "synth_eta_min": synth_eta_min,
        "by_lang": by_lang,
        "last_ingest": last.isoformat() if last else None,
    }


def publish_stories(limit: int = 80) -> int:
    """Upsert recent stories + a status snapshot into the world-news DB. Returns count published."""
    url = get_settings().world_news_db_url
    if not url:
        return 0
    with jarvis_connect() as jc:
        repo.prune_empty_stories(jc)  # drop orphan stories before publishing the read-model
        jc.commit()
        stories = repo.recent_stories(jc, limit=limit)
        ids = [s.id for s in stories]
        topics = repo.story_topics(jc, ids)         # section
        summaries = repo.story_summaries(jc, ids)   # tier-A fallback body
        sources = repo.story_sources(jc, ids)       # per-story outlet links (view original)
        stats = _status_snapshot(jc)
    with psycopg.connect(url) as sc:
        sc.execute(_DDL)
        sc.execute(_STATUS_DDL)
        for s in stories:
            body = s.synthesized_body or summaries.get(s.id, "")  # full synthesis, else tier-A
            # French is the default view; fall back to the original until it's translated (or if
            # the story is already French). The site can still reveal the original via the toggle.
            title_fr = s.title_fr or s.title
            body_fr = s.body_fr or body
            sc.execute(_UPSERT, (s.id, s.lang, s.title, body, title_fr, body_fr,
                                 topics.get(s.id, ""), Json(s.claims_json),
                                 Json(s.disagreements_json), s.source_count, s.origin_count,
                                 bool(s.synthesized_body), Json(sources.get(s.id, []))))
        # Reconcile: the read-model is exactly the current set — drop anything no longer published.
        # Guard on a non-empty set (an empty array would match ALL rows and wipe the table).
        if stories:
            sc.execute("DELETE FROM published_stories WHERE id <> ALL(%s)",
                       ([s.id for s in stories],))
        sc.execute(_STATUS_UPSERT, (Json(stats),))
        sc.commit()
    return len(stories)
