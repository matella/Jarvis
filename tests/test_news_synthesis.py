"""News tier-B synthesis — grounded write-up persisted; skips on empty (mocked LLM/repo)."""

from __future__ import annotations

from jarvis.news import synthesis
from jarvis.news.models import NewsArticle, NewsStory


def test_synthesize_persists_cited_writeup(monkeypatch) -> None:
    arts = [NewsArticle(source="Reuters", title="A", body="x"),
            NewsArticle(source="AP", title="B", body="y")]
    monkeypatch.setattr(synthesis.repo, "articles_for_story", lambda conn, sid: arts)
    saved = {}
    monkeypatch.setattr(synthesis.repo, "set_synthesis",
                        lambda conn, sid, **k: saved.update(k))
    result = {"title": "Synth", "body": "Para [1][2].",
              "claims": [{"claim": "c", "sources": [1]}], "disagreements": []}
    ok = synthesis.synthesize_story(None, NewsStory(id="nsty_1"),
                                    generate=lambda lang, a: result)
    assert ok is True
    assert saved["title"] == "Synth" and "[1]" in saved["body"] and saved["claims"]


def test_synthesize_skips_when_no_sources(monkeypatch) -> None:
    monkeypatch.setattr(synthesis.repo, "articles_for_story", lambda conn, sid: [])
    assert synthesis.synthesize_story(None, NewsStory(id="nsty_2"),
                                      generate=lambda lang, a: {"body": "x"}) is False


def test_synthesize_skips_when_model_empty(monkeypatch) -> None:
    monkeypatch.setattr(synthesis.repo, "articles_for_story",
                        lambda conn, sid: [NewsArticle(source="X", title="T", body="B")])
    assert synthesis.synthesize_story(None, NewsStory(id="nsty_3"),
                                      generate=lambda lang, a: {}) is False
