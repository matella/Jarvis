"""Capability status registry — config-driven availability + remedies. No DB."""

from __future__ import annotations

import pytest

from jarvis import capabilities


def _cfg(**over):
    base = dict(searxng_url="", imap_host="", mail_accounts=[], calendar_ics_urls=[],
                code_repo_allowlist=[], code_exec_enabled=False, hots_api_url="",
                hots_overlay_url="", orpheus_api_url="", world_news_url="", news_enabled=False)
    base.update(over)
    return type("S", (), base)()


def _patch(monkeypatch, *, cfg, token=None) -> None:
    monkeypatch.setattr(capabilities, "get_settings", lambda: cfg, raising=False)
    import jarvis.config
    monkeypatch.setattr(jarvis.config, "get_settings", lambda: cfg)
    monkeypatch.setattr("jarvis.security.secrets.get_provider",
                        lambda: type("P", (), {"get": lambda self, n, d=None: token})())


def test_always_on_capabilities(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, cfg=_cfg())
    for name in ("weather", "tasks", "notes", "recipes", "documents"):
        assert capabilities.available(name) is True
        assert capabilities.remedy(name) == ""


def test_gated_capabilities_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, cfg=_cfg())
    assert capabilities.available("email") is False
    assert capabilities.available("calendar") is False
    assert capabilities.available("web search") is False
    assert "IMAP" in capabilities.remedy("email")
    cal_remedy = capabilities.remedy("calendar")
    assert "google-oauth" in cal_remedy.lower() or "ICS" in cal_remedy


def test_gated_capabilities_turn_on_with_config(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, cfg=_cfg(imap_host="imap.gmail.com", searxng_url="http://searxng:8080"))
    assert capabilities.available("email") is True
    assert capabilities.available("web search") is True
    assert capabilities.available("deep research") is True


def test_calendar_on_via_google_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, cfg=_cfg(), token="1//refresh")
    assert capabilities.available("calendar") is True
