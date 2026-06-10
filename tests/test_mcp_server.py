"""Jarvis-as-MCP-server — tool functions (read-only, fault-tolerant) + server registration."""

from __future__ import annotations

from datetime import UTC, datetime

from jarvis.mcp import server as mcp_srv
from jarvis.news.models import NewsStory


class _Ctx:
    def __init__(self, v):
        self.v = v

    def __enter__(self):
        return self.v

    def __exit__(self, *a):
        return False


def test_news_returns_recent(monkeypatch) -> None:
    story = NewsStory(id="nsty_1", title="T", synthesized_body="Body", lang="fr", origin_count=3)
    monkeypatch.setattr(mcp_srv.db, "connect", lambda **k: _Ctx(object()))
    monkeypatch.setattr("jarvis.news.repository.recent_stories", lambda conn, limit: [story])
    monkeypatch.setattr("jarvis.news.repository.story_summaries", lambda conn, ids: {})
    out = mcp_srv.news()
    assert out[0]["title"] == "T" and out[0]["independent_sources"] == 3


def test_news_error_is_reported_not_raised(monkeypatch) -> None:
    monkeypatch.setattr(mcp_srv.db, "connect",
                        lambda **k: (_ for _ in ()).throw(RuntimeError("db down")))
    out = mcp_srv.news()
    assert "error" in out


def test_homelab_state_projects_rows(monkeypatch) -> None:
    class _Conn:
        def execute(self, sql, params=None):
            class _R:
                @staticmethod
                def fetchall():
                    return [{"entity": "container:web", "kind": "container",
                             "status": "running", "updated_at": datetime.now(UTC)}]
            return _R()

    monkeypatch.setattr(mcp_srv.db, "connect", lambda **k: _Ctx(_Conn()))
    out = mcp_srv.homelab_state()
    assert out[0]["entity"] == "container:web" and out[0]["status"] == "running"


def test_recall_facts(monkeypatch) -> None:
    class _F:
        key, value = "city", "Liège"

    monkeypatch.setattr(mcp_srv.db, "connect", lambda **k: _Ctx(object()))
    monkeypatch.setattr("jarvis.memory.facts.list_facts", lambda conn: [_F()])
    out = mcp_srv.recall()
    assert out["facts"] == [{"key": "city", "value": "Liège"}]


def test_ask_runs_conversation(monkeypatch) -> None:
    class _Result:
        message = "Bonjour."

        class route:  # noqa: N801 — mimic TurnRoute enum member
            value = "answer"

    monkeypatch.setattr(mcp_srv.db, "connect", lambda **k: _Ctx(object()))
    monkeypatch.setattr("jarvis.conversation.store.start_conversation",
                        lambda conn, actor: object())
    monkeypatch.setattr("jarvis.agents.conversation.respond",
                        lambda conn, session, q: _Result())
    out = mcp_srv.ask("salut ?")
    assert out == {"answer": "Bonjour.", "route": "answer"}
    assert mcp_srv.ask("") == {"error": "empty question"}


def test_build_server_registers_five_tools() -> None:
    srv = mcp_srv.build_server()
    import asyncio
    tools = asyncio.run(srv.list_tools())
    names = sorted(t.name for t in tools)
    assert names == ["jarvis_ask", "jarvis_homelab_state", "jarvis_news",
                     "jarvis_recall", "jarvis_recent_events"]
