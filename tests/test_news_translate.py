"""News translation — local-model FR translation, fault-tolerant fallback, and the worker."""

from __future__ import annotations

from jarvis.news import translate


def test_translate_falls_back_on_failure(monkeypatch) -> None:
    # Any model error → return the source text unchanged (never blocks publishing).
    def boom(*a, **k):
        raise RuntimeError("model down")
    monkeypatch.setattr("jarvis.models.scheduler.chat", boom)
    assert translate.translate_to_fr("Hello", "World") == ("Hello", "World", [])


def test_translate_uses_model_output(monkeypatch) -> None:
    monkeypatch.setattr(
        "jarvis.models.scheduler.chat",
        lambda *a, **k: {"message": {"content": '{"title": "Bonjour", "body": "Le monde"}'}},
    )
    assert translate.translate_to_fr("Hello", "World") == ("Bonjour", "Le monde", [])


def test_source_hash_changes_with_content() -> None:
    assert translate.source_hash("a", "b") != translate.source_hash("a", "c")
    assert translate.source_hash("a", "b") == translate.source_hash("a", "b")


def test_translate_pending_translates_and_stores(monkeypatch) -> None:
    from jarvis.news import worker
    from jarvis.news.models import NewsStory

    monkeypatch.setattr(worker, "get_settings",
                        lambda: type("S", (), {"news_enabled": True, "news_default_lang": "fr"})())

    class _Conn:
        def __init__(self): self.commits = 0
        def commit(self): self.commits += 1
        def rollback(self): pass

    conn = _Conn()
    monkeypatch.setattr(worker.db, "connect",
                        lambda: type("Ctx", (), {"__enter__": lambda s: conn,
                                                 "__exit__": lambda s, *a: False})())
    monkeypatch.setattr("jarvis.news.repository.untranslated_stories",
                        lambda conn, *, default_lang, limit=5: [
                            NewsStory(id="nsty_1", lang="en", title="Hi", synthesized_body="Body")])
    monkeypatch.setattr("jarvis.news.repository.story_summaries", lambda conn, ids: {})
    monkeypatch.setattr("jarvis.news.translate.translate_to_fr",
                        lambda t, b, d=None: ("Salut", "Corps", []))
    saved = {}
    monkeypatch.setattr("jarvis.news.repository.set_translation",
                        lambda conn, sid, **k: saved.update(k))
    assert worker.translate_pending() == 1
    assert saved["title_fr"] == "Salut" and saved["body_fr"] == "Corps"
