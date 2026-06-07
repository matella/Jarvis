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
