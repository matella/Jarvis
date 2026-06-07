"""World News connector + present routing — skeleton status (mocked)."""

from __future__ import annotations

from jarvis.agents import conversation as convo


def test_present_world_news_not_reachable(monkeypatch) -> None:
    monkeypatch.setattr("jarvis.connectors.world_news.reachable", lambda: False)
    out = convo._present_world_news()
    assert "isn't connected" in out.message or "reach" in out.message.lower()


def test_present_world_news_skeleton(monkeypatch) -> None:
    monkeypatch.setattr("jarvis.connectors.world_news.reachable", lambda: True)
    monkeypatch.setattr("jarvis.connectors.world_news.hello", lambda: "Hello from API Gateway")
    out = convo._present_world_news()
    assert "skeleton" in out.message and "Hello from API Gateway" in out.message
