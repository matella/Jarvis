"""Session enforcement: a configured passphrase makes a valid session mandatory (no open dev)."""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from jarvis.gateway import deps
from jarvis.gateway.auth import AuthError


@contextmanager
def _conn_with(session_ok: bool):
    class _C:
        pass
    yield _C()


def _patch(monkeypatch, *, passphrase: bool, session_ok: bool, gateway_token: str = "") -> None:
    monkeypatch.setattr(deps, "get_settings",
                        lambda: type("S", (), {"app_session_cookie": "jarvis_session",
                                               "gateway_actor": "local",
                                               "gateway_token": gateway_token})())
    monkeypatch.setattr("jarvis.security.secrets.get_provider",
                        lambda: type("P", (), {"get": lambda self, n, d=None: "scrypt$x$y"
                                               if passphrase else None})())
    monkeypatch.setattr(deps.sessions, "resolve_session", lambda conn, tok: session_ok)
    monkeypatch.setattr(deps.db, "connect", lambda: _conn_with(session_ok))


def test_valid_session_authenticates(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, passphrase=True, session_ok=True)
    p = deps.resolve_principal("good-token", None)
    assert p.actor == "local" and p.has("chat")


def test_passphrase_set_no_session_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, passphrase=True, session_ok=False)
    with pytest.raises(AuthError):
        deps.resolve_principal(None, None)  # login required → no open-dev fallback
    with pytest.raises(AuthError):
        deps.resolve_principal("stale-token", None)


def test_no_passphrase_falls_back_to_open_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, passphrase=False, session_ok=False, gateway_token="")
    p = deps.resolve_principal(None, None)  # open dev mode (no token configured)
    assert p.actor == "local"


def test_login_required_reflects_passphrase(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("jarvis.security.secrets.get_provider",
                        lambda: type("P", (), {"get": lambda self, n, d=None: "scrypt$x$y"})())
    assert deps.login_required() is True
    monkeypatch.setattr("jarvis.security.secrets.get_provider",
                        lambda: type("P", (), {"get": lambda self, n, d=None: None})())
    assert deps.login_required() is False
