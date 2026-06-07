"""News ingest — idempotent store + spine event (mocked repo/emit, no DB)."""

from __future__ import annotations

from jarvis.news import ingest


def test_ingest_new_article_emits_event(monkeypatch) -> None:
    events = []
    monkeypatch.setattr(ingest.repo, "get_by_hash_id", lambda conn, h: None)  # not seen before
    monkeypatch.setattr(ingest.repo, "upsert_article", lambda conn, art: art.with_hash())
    monkeypatch.setattr(ingest, "emit_event", lambda e: events.append(e))
    aid = ingest.ingest_article(None, source="Reuters", title="T", body="B", url="https://r.com/a")
    assert aid is not None
    assert events and events[0].type == "news.article_scraped"
    assert events[0].payload["article_id"] == aid


def test_ingest_duplicate_is_noop(monkeypatch) -> None:
    events = []
    monkeypatch.setattr(ingest.repo, "get_by_hash_id", lambda conn, h: "nart_existing")  # seen
    monkeypatch.setattr(ingest.repo, "upsert_article", lambda conn, art: art.with_hash())
    monkeypatch.setattr(ingest, "emit_event", lambda e: events.append(e))
    aid = ingest.ingest_article(None, source="AP", title="T", body="B", url="https://r.com/a")
    assert aid is None and events == []   # duplicate → no event


def test_process_pending_disabled_is_noop(monkeypatch) -> None:
    from jarvis.news import worker
    monkeypatch.setattr(worker, "get_settings", lambda: type("S", (), {"news_enabled": False})())
    assert worker.process_pending() == 0
