"""6a unit: gateway bearer-token auth + scope resolution."""

from __future__ import annotations

import pytest

from jarvis.gateway import auth


class _Cfg:
    def __init__(self, token: str, actor: str = "local") -> None:
        self.gateway_token = token
        self.gateway_actor = actor


def test_open_dev_mode_grants_local_all_scopes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: _Cfg(""))
    p = auth.authenticate(None)  # no header needed in open mode
    assert p.actor == "local"
    assert p.has("read") and p.has("chat")


def test_token_required_rejects_missing_and_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: _Cfg("s3cret"))
    with pytest.raises(auth.AuthError):
        auth.authenticate(None)
    with pytest.raises(auth.AuthError):
        auth.authenticate("Bearer wrong")
    with pytest.raises(auth.AuthError):
        auth.authenticate("Basic s3cret")  # wrong scheme


def test_token_required_accepts_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: _Cfg("s3cret", actor="matthieu"))
    p = auth.authenticate("Bearer s3cret")
    assert p.actor == "matthieu"
    assert p.scopes == auth.ALL_SCOPES
