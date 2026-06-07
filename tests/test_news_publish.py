"""News publish — no-op when unconfigured; upserts recent stories into the site DB (mocked)."""

from __future__ import annotations

from jarvis.news import publish
from jarvis.news.models import NewsStory


class _Ctx:
    def __init__(self, v):
        self.v = v

    def __enter__(self):
        return self.v

    def __exit__(self, *a):
        return False


class _SiteConn(_Ctx):
    def __init__(self, log):
        super().__init__(self)
        self.log = log

    def execute(self, sql, params=None):
        self.log.append((sql, params))

    def commit(self):
        pass


def test_publish_noop_when_no_url(monkeypatch) -> None:
    monkeypatch.setattr(publish, "get_settings", lambda: type("S", (), {"world_news_db_url": ""})())
    assert publish.publish_stories() == 0


def test_publish_upserts_recent(monkeypatch) -> None:
    monkeypatch.setattr(publish, "get_settings",
                        lambda: type("S", (), {"world_news_db_url": "postgresql://x"})())
    monkeypatch.setattr(publish, "jarvis_connect",
                        lambda: _Ctx(type("C", (), {"commit": lambda s: None})()))
    monkeypatch.setattr(publish.repo, "prune_empty_stories", lambda conn: 0)
    monkeypatch.setattr(publish.repo, "story_topics", lambda conn, ids: {"nsty_1": "world"})
    monkeypatch.setattr(publish.repo, "story_summaries", lambda conn, ids: {"nsty_1": "sum"})
    monkeypatch.setattr(publish, "_status_snapshot", lambda jc: {"articles": 1})
    monkeypatch.setattr(publish.repo, "recent_stories",
                        lambda conn, **k: [NewsStory(id="nsty_1", title="T", synthesized_body="B")])
    executed: list = []
    monkeypatch.setattr(publish.psycopg, "connect", lambda url: _SiteConn(executed))
    n = publish.publish_stories()
    assert n == 1
    assert any("published_stories" in sql for sql, _ in executed)  # DDL + upsert ran
