"""News fetch — source allowlist + RSS→FetchedItem mapping (mocked egress, no network)."""

from __future__ import annotations

from jarvis.connectors.feeds import FeedItem
from jarvis.news import fetch
from jarvis.news.sources import source_hosts


def test_source_hosts_extracted() -> None:
    hosts = source_hosts()
    assert "feeds.bbci.co.uk" in hosts and "www.vrt.be" in hosts


def test_fetch_skips_non_allowlisted(monkeypatch) -> None:
    monkeypatch.setattr(fetch, "allowed", lambda host: False)  # nothing allowlisted
    assert fetch.fetch_all() == []


def test_fetch_maps_feed_items(monkeypatch) -> None:
    monkeypatch.setattr(fetch, "allowed", lambda host: True)
    resp = type("R", (), {"read": lambda s: b"<xml/>"})()
    monkeypatch.setattr(fetch, "guarded_request", lambda u, **k: resp)
    monkeypatch.setattr(fetch, "parse_feed",
                        lambda body: [FeedItem(guid="g", title="Headline", link="http://x/a",
                                               summary="Body text")])
    items = fetch.fetch_all()
    assert items and items[0].title == "Headline" and items[0].body == "Body text"
    assert items[0].url == "http://x/a"
