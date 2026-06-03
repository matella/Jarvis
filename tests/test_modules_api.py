"""Gateway module REST — routing, serialization, validation, tool-reuse. No live DB (mocked)."""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from starlette.testclient import TestClient

import jarvis.gateway.app as appmod
from jarvis.tasks.models import Task


@contextmanager
def _fake_conn(*_a, **_k):
    yield object()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # Open dev mode (no gateway_token) → principal resolves to the local actor without a DB hit.
    monkeypatch.setattr("jarvis.db.connect", _fake_conn)
    return TestClient(appmod.app)


def test_list_tasks_serializes(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("jarvis.tasks.repository.list_open",
                        lambda conn, **k: [Task(title="Pay rent")])
    resp = client.get("/api/tasks")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["title"] == "Pay rent" and body[0]["status"] == "open"


def test_create_task_roundtrips(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("jarvis.tasks.repository.create", lambda conn, task, **k: task)
    resp = client.post("/api/tasks", json={"title": "Buy milk", "priority": "high"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "Buy milk" and resp.json()["priority"] == "high"


def test_create_task_validation_is_400(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("jarvis.tasks.repository.create", lambda conn, task, **k: task)
    resp = client.post("/api/tasks", json={"title": "   "})  # empty title → model rejects
    assert resp.status_code == 400


def test_create_note_roundtrips(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("jarvis.notes.repository.create", lambda conn, note, **k: note)
    resp = client.post("/api/notes", json={"body_md": "# Idea\nbuild it", "tags": ["x"]})
    assert resp.status_code == 200 and resp.json()["title"] == "Idea"


def test_research_post_reuses_the_gated_tool(client: TestClient, monkeypatch: pytest.MonkeyPatch
                                             ) -> None:
    calls: list = []

    class _FakeTool:
        timeout_seconds = 600

        def run(self, target, *, timeout_s):
            calls.append(target)
            return {"run_id": "rsch_1", "status": "done", "document_id": "doc_1"}

    monkeypatch.setattr("jarvis.tools.registry.get_tool", lambda name: _FakeTool())
    resp = client.post("/api/research", json={"query": "why blue sky", "depth": "quick"})
    assert resp.status_code == 200 and resp.json()["run_id"] == "rsch_1"
    assert calls[0] == {"query": "why blue sky", "depth": "quick"}  # None values stripped


def test_tool_validation_error_is_400(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    class _BadTool:
        timeout_seconds = 30

        def run(self, target, *, timeout_s):
            raise ValueError("recipe url is required")

    monkeypatch.setattr("jarvis.tools.registry.get_tool", lambda name: _BadTool())
    resp = client.post("/api/recipes/import", json={})
    assert resp.status_code == 400


def test_set_model_pref_validates_backend(client: TestClient, monkeypatch: pytest.MonkeyPatch
                                          ) -> None:
    resp = client.put("/api/models/prefs", json={"action": "postmortem", "backend": "gpt-9"})
    assert resp.status_code == 400  # invalid backend rejected before any DB write


def test_routine_enable_disable(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list = []
    monkeypatch.setattr("jarvis.routines.repository.set_enabled",
                        lambda conn, rid, enabled: bool(seen.append((rid, enabled))) or True)
    assert client.post("/api/routines/rtn_1/disable").json() == {"id": "rtn_1", "enabled": False}
    assert client.post("/api/routines/rtn_1/enable").json()["enabled"] is True
    assert seen == [("rtn_1", False), ("rtn_1", True)]


def test_routine_unknown_op_is_400(client: TestClient) -> None:
    assert client.post("/api/routines/rtn_1/frobnicate").status_code == 400


def test_get_mail_returns_full_body(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from jarvis.mail.models import CachedMessage
    msg = CachedMessage(account="default", uid="1", from_addr="a@b.com", subject="Hi",
                        body_text="the full body text")
    monkeypatch.setattr("jarvis.mail.repository.get", lambda conn, mid: msg)
    resp = client.get("/api/mail/mail_1")
    assert resp.status_code == 200 and resp.json()["body_text"] == "the full body text"
    monkeypatch.setattr("jarvis.mail.repository.get", lambda conn, mid: None)
    assert client.get("/api/mail/nope").status_code == 404


def test_send_mail_reuses_gated_tool(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list = []

    class _Tool:
        timeout_seconds = 30

        def run(self, target, *, timeout_s):
            sent.append(target)
            return {"sent_to": target["to"]}

    monkeypatch.setattr("jarvis.tools.registry.get_tool", lambda name: _Tool())
    resp = client.post("/api/mail/send", json={"to": "x@y.com", "subject": "Re: hi", "body": "ok"})
    assert resp.status_code == 200 and resp.json()["sent_to"] == "x@y.com"
    assert sent[0] == {"to": "x@y.com", "subject": "Re: hi", "body": "ok"}
