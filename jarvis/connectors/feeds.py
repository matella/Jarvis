"""RSS / Atom feeds → `feed.item` events. Read-only; the simplest read connector.

Parsing is pure (stdlib `xml.etree`) and unit-tested on sample XML. Fetching goes through the egress
allowlist; every title/summary is `sanitize()`d before it touches the spine. New items are deduped
against the events table by a stable `feed:<guid>` entity_ref, so a re-poll doesn't replay history.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from xml.etree import ElementTree as ET

from jarvis import db, ids
from jarvis.config import get_settings
from jarvis.connectors.base import register_connector
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import emit_event
from jarvis.security.egress import guarded_request
from jarvis.security.sanitize import sanitize

_ATOM = "{http://www.w3.org/2005/Atom}"


@dataclass(frozen=True)
class FeedItem:
    guid: str
    title: str
    link: str
    summary: str


def _text(el: ET.Element | None) -> str:
    return (el.text or "").strip() if el is not None else ""


def _atom_link(links: list) -> str:
    """The HTML article URL from an Atom entry's <link>s. Entries carry several — the article, a
    per-article feed (.rss.xml, type=*+xml), an enclosure image, etc. Prefer an explicit
    rel=alternate; skip feed/enclosure/self links. (VRT's first link is a .rss.xml feed and its real
    article is an explicit rel=alternate shortlink, so 'first / no-rel' grabbed the feed.)"""
    explicit_alt = ""
    fallback = ""
    for le in links:
        rel = le.get("rel", "")
        href = le.get("href", "")
        typ = le.get("type", "")
        if not href or rel in ("self", "edit", "enclosure", "replies", "via"):
            continue
        if "+xml" in typ or href.endswith((".rss.xml", ".atom", ".xml")):
            continue  # a feed/machine link, not the readable article
        if rel == "alternate":
            explicit_alt = explicit_alt or href
        fallback = fallback or href
    return explicit_alt or fallback


def parse_feed(xml: bytes) -> list[FeedItem]:
    """Parse RSS 2.0 or Atom into normalized, sanitized items. Pure — no I/O."""
    root = ET.fromstring(xml)
    items: list[FeedItem] = []
    # RSS: <rss><channel><item>...  ·  Atom: <feed><entry>...
    rss_items = root.findall(".//item")
    if rss_items:
        for it in rss_items:
            link = _text(it.find("link"))
            guid = _text(it.find("guid")) or link or _text(it.find("title"))
            items.append(FeedItem(
                guid=guid, title=sanitize(_text(it.find("title"))),
                link=link, summary=sanitize(_text(it.find("description"))),
            ))
        return items
    for entry in root.findall(f"{_ATOM}entry"):
        link = _atom_link(entry.findall(f"{_ATOM}link"))
        guid = _text(entry.find(f"{_ATOM}id")) or link
        items.append(FeedItem(
            guid=guid, title=sanitize(_text(entry.find(f"{_ATOM}title"))),
            link=link, summary=sanitize(_text(entry.find(f"{_ATOM}summary"))),
        ))
    return items


def _already_seen(conn, entity_ref: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM events WHERE entity_ref = %s LIMIT 1", (entity_ref,)
    ).fetchone()
    return row is not None


def _emit_item(conn, item: FeedItem, source_url: str) -> bool:
    entity_ref = f"feed:{item.guid}"
    if _already_seen(conn, entity_ref):
        return False
    emit_event(Event(
        type="feed.item", severity=Severity.info, source="feeds", entity_ref=entity_ref,
        occurred_at=utcnow(),
        payload={"title": item.title, "link": item.link, "summary": item.summary[:500],
                 "feed": source_url},
        correlation_id=ids.new_id(ids.CORRELATION),
    ))
    return True


def poll_once() -> int:
    """Fetch every configured feed, emit new items. Returns count emitted."""
    s = get_settings()
    emitted = 0
    with db.connect() as conn:
        for url in s.feed_urls:
            try:
                body = guarded_request(url, timeout=15).read()
            except Exception as exc:  # noqa: BLE001 — egress-blocked or fetch error; skip this feed
                print(f"[feeds] {url} failed: {exc!r}", flush=True)
                continue
            for item in parse_feed(body)[: s.feed_max_items]:
                if _emit_item(conn, item, url):
                    emitted += 1
    return emitted


class FeedsConnector:
    name = "feeds"

    def ingest(self, *, once: bool = True) -> int:
        return poll_once()


def run_feeds(*, once: bool = False) -> None:
    interval = get_settings().feed_poll_interval_s
    while True:
        count = poll_once()
        if count:
            print(f"[feeds] emitted {count} new items", flush=True)
        if once:
            return
        time.sleep(interval)


register_connector(FeedsConnector())
