"""News ingest — the one entry point for a scraped article. Upsert + emit the spine event.

External content enters as an event (Hard Rule 3): we store the raw article (idempotent on
canonical_hash) and emit `news.article_scraped`. Enrichment (embed/pool/tier-A) is done separately
by the processing worker, draining the embedding-NULL backlog at background pace.
"""

from __future__ import annotations

from datetime import datetime

import psycopg

from jarvis import ids
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import emit_event
from jarvis.news import repository as repo
from jarvis.news.models import NewsArticle


def ingest_article(
    conn: psycopg.Connection,
    *,
    source: str,
    title: str,
    body: str,
    url: str = "",
    lang: str = "en",
    published_at: datetime | None = None,
) -> str | None:
    """Store a scraped article (idempotent) and emit the spine event. Returns the article id, or
    None if it was a duplicate of one already stored."""
    art = NewsArticle(source=source, title=title, body=body, url=url, lang=lang,
                      published_at=published_at).with_hash()
    before = repo.get_by_hash_id(conn, art.canonical_hash)
    stored = repo.upsert_article(conn, art)
    if before is not None:
        return None  # duplicate — already ingested
    emit_event(
        Event(
            type="news.article_scraped", severity=Severity.debug, source="news",
            entity_ref=stored.entity_ref, occurred_at=stored.published_at or utcnow(),
            payload={"article_id": stored.id, "news_source": source, "lang": lang},
            correlation_id=ids.new_id(ids.CORRELATION),
        )
    )
    return stored.id
