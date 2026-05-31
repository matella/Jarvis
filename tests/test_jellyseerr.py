"""Jellyseerr gated tools — registration, validation, search parsing. No live WebUI."""

from __future__ import annotations

import pytest

from jarvis.connectors import jellyseerr as js
from jarvis.tools.contract import Rollback
from jarvis.tools.registry import get_tool


def test_tools_registered_with_contracts() -> None:
    req = get_tool("jellyseerr.request")
    assert req and req.side_effects is True and req.rollback is Rollback.none and req.preview
    appr = get_tool("jellyseerr.approve")
    assert appr and appr.side_effects is True and appr.idempotent is True


def test_request_requires_a_query() -> None:
    with pytest.raises(ValueError):
        js._require_query({})
    assert js._require_query({"query": " Dune "}) == "Dune"
    assert js._require_query({"title": "Andor"}) == "Andor"


def test_approve_requires_numeric_id() -> None:
    assert js._require_request_id({"request_id": 42}) == "42"
    with pytest.raises(ValueError):
        js._require_request_id({"request_id": "not-a-number"})
    with pytest.raises(ValueError):
        js._require_request_id({})


def test_top_match_picks_first_movie_or_tv_and_sanitizes(monkeypatch) -> None:
    monkeypatch.setattr(js, "_api", lambda *a, **k: {"results": [
        {"mediaType": "person", "id": 1, "name": "Some Director"},  # skipped
        {"mediaType": "movie", "id": 693134, "title": "Dune: Part Two email a@b.com"},
    ]})
    m = js._top_match("Dune Part Two")
    assert m["tmdb_id"] == 693134 and m["media_type"] == "movie"
    assert "a@b.com" not in m["title"]  # TMDB text sanitized before it reaches the model


def test_top_match_none_when_no_media(monkeypatch) -> None:
    monkeypatch.setattr(js, "_api", lambda *a, **k: {"results": [{"mediaType": "person", "id": 1}]})
    assert js._top_match("nobody") is None
