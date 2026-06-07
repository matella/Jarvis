"""News fetcher — pull the configured RSS sources (SSRF-guarded) into FetchedItems.

v1 uses the feed's own title+summary as the article text (no per-article page fetch) — fast, no
heavy readability dep, minimal egress surface. Full-page readability is a documented later upgrade.
Reuses the codebase's `parse_feed` (RSS+Atom, sanitized) and the SSRF-safe `guarded_request`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit

from jarvis.connectors.feeds import parse_feed
from jarvis.news.sources import SOURCES
from jarvis.security.egress import allowed, guarded_request


@dataclass(frozen=True)
class FetchedItem:
    source: str
    title: str
    body: str
    url: str
    lang: str
    published_at: datetime | None = None


def _fetch_source(rss_url: str, *, timeout: float = 15.0) -> list:
    host = (urlsplit(rss_url).hostname or "").lower()
    if not allowed(host):
        return []  # not egress-allowlisted → skip (operator must allowlist news source domains)
    try:
        body = guarded_request(rss_url, timeout=timeout).read()
        return parse_feed(body)
    except Exception:  # noqa: BLE001 — a flaky feed must not stop the others
        return []


def fetch_all(*, per_source: int = 30) -> list[FetchedItem]:
    """Every configured source's recent items as FetchedItems. Skips empty/unreachable feeds."""
    out: list[FetchedItem] = []
    for src in SOURCES:
        for it in _fetch_source(src.rss_url)[:per_source]:
            text = (it.summary or it.title).strip()
            if not text:
                continue
            out.append(FetchedItem(source=src.name, title=it.title, body=text, url=it.link,
                                   lang=src.lang))
    return out
