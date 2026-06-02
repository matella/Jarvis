"""Gateway login/logout endpoints — passphrase gate, token mint, cookie, revoke. No live DB."""

from __future__ import annotations

import types
from contextlib import contextmanager

import pytest
from starlette.testclient import TestClient

import jarvis.gateway.app as appmod
from jarvis.gateway import sessions


@contextmanager
def _fake_conn():
    yield object()


@pytest.fixture
def stored_hash(monkeypatch: pytest.MonkeyPatch) -> str:
    stored = sessions.hash_passphrase("hunter2")
    monkeypatch.setattr(appmod.db, "connect", _fake_conn)
    monkeypatch.setattr(
        "jarvis.security.secrets.get_provider",
        lambda: types.SimpleNamespace(get=lambda name, default=None: stored),
    )
    return stored


def test_login_rejects_bad_passphrase(stored_hash: str) -> None:
    resp = TestClient(appmod.app).post("/api/login", json={"passphrase": "wrong"})
    assert resp.status_code == 401


def test_login_mints_token_and_sets_cookie(
    stored_hash: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sessions, "mint_session", lambda conn, **k: "TOK123")
    resp = TestClient(appmod.app).post("/api/login", json={"passphrase": "hunter2"})
    assert resp.status_code == 200
    assert resp.json()["token"] == "TOK123"  # returned for the cross-origin native app
    cookie = resp.headers.get("set-cookie", "")
    assert "jarvis_session=" in cookie and "HttpOnly" in cookie  # browser path


def test_logout_revokes_and_clears(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(appmod.db, "connect", _fake_conn)
    revoked: list[str] = []
    monkeypatch.setattr(sessions, "revoke_session", lambda conn, tok: revoked.append(tok))
    resp = TestClient(appmod.app).post(
        "/api/logout", headers={"Authorization": "Bearer TOK123"}
    )
    assert resp.status_code == 200
    assert revoked == ["TOK123"]
