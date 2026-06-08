"""News daemon workers — registered by the supervisor, each manages its own connection.

`process_pending` drains the enrichment backlog (embedding-NULL articles) in bounded batches so it
keeps pace with the GPU/CPU without ever blocking ingest. `scrape_once` polls the configured RSS
sources and ingests new items. Both no-op unless `news_enabled`.
"""

from __future__ import annotations

from jarvis import db
from jarvis.config import get_settings
from jarvis.news import reactor
from jarvis.news import repository as repo


def process_pending() -> int:
    """Enrich up to one bounded batch of stored-but-unprocessed articles. Returns the count done."""
    if not get_settings().news_enabled:
        return 0
    done = 0
    with db.connect() as conn:
        for article_id in repo.pending_article_ids(conn, limit=20):
            try:
                reactor.process_article(conn, article_id)
                conn.commit()  # commit per article so the new story is INDEXED before the next
                done += 1      # one is clustered against — otherwise same-batch dupes never merge
            except Exception:  # noqa: BLE001 — one bad article must not stall the backlog
                conn.rollback()
                continue
    return done


def synthesize_pending(limit: int = 3) -> int:
    """Full tier-B synthesis for a few multi-source stories that don't have one yet (bounded so
    it never floods the LLM). Runs continuously so cross-outlet stories get the full write-up
    without waiting for the daily edition. Returns the count synthesised."""
    if not get_settings().news_enabled:
        return 0
    from jarvis.news import repository as r
    from jarvis.news import synthesis

    done = 0
    with db.connect() as conn:
        for story in r.stories_awaiting_synthesis(conn, limit=limit):
            try:
                if synthesis.synthesize_story(conn, story):
                    conn.commit()
                    done += 1
                else:
                    conn.rollback()
            except Exception:  # noqa: BLE001 — one bad synthesis must not stall the queue
                conn.rollback()
    return done


def translate_pending(limit: int = 8) -> int:
    """Translate a few not-yet-translated, non-French stories into French (title + display body)
    on the local model. Bounded + cached on the story, so steady state is cheap. Returns the count
    translated."""
    s = get_settings()
    if not s.news_enabled:
        return 0
    from jarvis.news import repository as r
    from jarvis.news import translate

    done = 0
    with db.connect() as conn:
        stories = r.untranslated_stories(conn, default_lang=s.news_default_lang, limit=limit)
        if not stories:
            return 0
        summaries = r.story_summaries(conn, [st.id for st in stories])
        for st in stories:
            body = st.synthesized_body or summaries.get(st.id, "")
            if not (st.title or body):
                continue  # no content yet — translate once it has some
            try:
                title_fr, body_fr = translate.translate_to_fr(st.title, body)
                r.set_translation(conn, st.id, title_fr=title_fr, body_fr=body_fr,
                                  h=translate.source_hash(st.title, body))
                conn.commit()
                done += 1
            except Exception:  # noqa: BLE001 — one bad translation must not stall the queue
                conn.rollback()
    return done


def scrape_once() -> int:
    """Fetch the configured sources and ingest new items. Returns the count newly ingested."""
    if not get_settings().news_enabled:
        return 0
    from jarvis.news.fetch import fetch_all
    from jarvis.news.ingest import ingest_article

    count = 0
    with db.connect() as conn:
        for item in fetch_all():
            if ingest_article(conn, source=item.source, title=item.title, body=item.body,
                              url=item.url, lang=item.lang, published_at=item.published_at):
                count += 1
    return count
