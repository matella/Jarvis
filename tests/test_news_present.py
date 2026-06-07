"""News present route — top stories / search / not-enabled (mocked repo + config)."""

from __future__ import annotations

from jarvis.agents import conversation as convo
from jarvis.news.models import NewsStory


def _enable(monkeypatch):
    monkeypatch.setattr(convo, "get_settings",
                        lambda: type("S", (), {"news_enabled": True})())


def test_present_news_disabled(monkeypatch) -> None:
    monkeypatch.setattr(convo, "get_settings", lambda: type("S", (), {"news_enabled": False})())
    out = convo._present_news(conn=None, utterance="what's the world news")
    assert "isn't connected" in out.message or "enable" in out.message.lower()


def test_present_news_top_stories(monkeypatch) -> None:
    _enable(monkeypatch)
    monkeypatch.setattr("jarvis.news.repository.recent_stories",
                        lambda conn, **k: [NewsStory(title="EU AI Act timeline", origin_count=11)])
    out = convo._present_news(conn=None, utterance="what's the world news")
    assert out.artifacts and out.artifacts[0].title == "World news"
    assert out.artifacts[0].data  # rendered


def test_present_news_search_about_topic(monkeypatch) -> None:
    _enable(monkeypatch)
    seen = {}
    monkeypatch.setattr("jarvis.news.embedding.embed_news",
                        lambda t: seen.setdefault("q", t) or [0.1, 0.2])
    monkeypatch.setattr("jarvis.news.repository.search_stories",
                        lambda conn, vec, **k: [NewsStory(title="Brexit latest", origin_count=4)])
    out = convo._present_news(conn=None, utterance="show me the news about Brexit")
    assert seen["q"] == "Brexit"                       # embedded the topic
    assert out.artifacts[0].title == "News · Brexit"


def test_present_news_empty(monkeypatch) -> None:
    _enable(monkeypatch)
    monkeypatch.setattr("jarvis.news.repository.recent_stories", lambda conn, **k: [])
    out = convo._present_news(conn=None, utterance="what's the world news")
    assert "No news pooled yet" in out.message
