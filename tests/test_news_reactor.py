"""News reactor — embed/pool/tier-A, with the efficiency invariant (only the representative
gets summarized). Repo + models + LLM all mocked; no DB."""

from __future__ import annotations

from jarvis.news import reactor
from jarvis.news.models import NewsArticle


def _settings():
    return type("S", (), {"news_sim_threshold": 0.82, "news_enabled": True})()


def test_representative_is_summarized(monkeypatch) -> None:
    art = NewsArticle(id="nart_1", source="Reuters", title="T", body="B", lang="en")
    monkeypatch.setattr(reactor.repo, "get_article", lambda conn, aid: art)
    monkeypatch.setattr(reactor.repo, "nearest_story", lambda conn, vec, **k: None)  # -> new story
    monkeypatch.setattr(reactor.repo, "create_story", lambda conn, s: s)
    enriched: dict = {}
    monkeypatch.setattr(reactor.repo, "enrich_article", lambda conn, aid, **k: enriched.update(k))
    monkeypatch.setattr(reactor.repo, "refresh_story_counts", lambda conn, sid: None)
    monkeypatch.setattr(reactor, "get_settings", _settings)
    sid = reactor.process_article(None, "nart_1", embed=lambda t: [0.1, 0.2],
                                  summarize=lambda *a: ("sum", "tech", "world"))
    assert sid and enriched["summary"] == "sum" and enriched["topic"] == "tech"


def test_duplicate_joins_without_summarizing(monkeypatch) -> None:
    art = NewsArticle(id="nart_2", source="AP", title="T", body="B", lang="en")
    monkeypatch.setattr(reactor.repo, "get_article", lambda conn, aid: art)
    monkeypatch.setattr(reactor.repo, "nearest_story", lambda conn, vec, **k: "nsty_existing")
    monkeypatch.setattr(reactor.repo, "enrich_article", lambda conn, aid, **k: None)
    monkeypatch.setattr(reactor.repo, "refresh_story_counts", lambda conn, sid: None)
    monkeypatch.setattr(reactor, "get_settings", _settings)
    flags = {"summarized": False}

    def summarize(*a):
        flags["summarized"] = True
        return ("x", "y", "z")

    sid = reactor.process_article(None, "nart_2", embed=lambda t: [0.1, 0.2], summarize=summarize)
    assert sid == "nsty_existing"
    assert flags["summarized"] is False  # joined an existing story → NOT re-summarized
