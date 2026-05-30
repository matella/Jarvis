"""Backlog #10 unit: plugin manifest validation + safe template rendering."""

from __future__ import annotations

import pytest

from jarvis.plugins.loader import (
    PluginError,
    PluginManifest,
    build_tool,
    render,
    validate_manifest,
)
from jarvis.tools.contract import Rollback


def _manifest(**kw) -> PluginManifest:
    base = dict(name="ha.scene", url="http://ha.lan/api/scenes/{scene}", args=["scene"])
    base.update(kw)
    return PluginManifest(**base)


def test_valid_manifest() -> None:
    validate_manifest(_manifest())  # no raise


def test_rejects_bad_intent_type() -> None:
    with pytest.raises(PluginError, match="entity.verb"):
        validate_manifest(_manifest(name="notvalid"))


def test_rejects_undeclared_template_arg() -> None:
    with pytest.raises(PluginError, match="undeclared args"):
        validate_manifest(_manifest(url="http://ha.lan/{scene}/{secret}", args=["scene"]))


def test_render_substitutes_allowed_scalar() -> None:
    assert render("http://ha.lan/{scene}", {"scene": "movie"}, ["scene"]) == "http://ha.lan/movie"


def test_render_rejects_unknown_and_nonscalar() -> None:
    with pytest.raises(PluginError, match="not allowed"):
        render("http://x/{evil}", {"evil": "y"}, ["scene"])
    with pytest.raises(PluginError, match="missing"):
        render("http://x/{scene}", {}, ["scene"])
    with pytest.raises(PluginError, match="scalar"):
        render("http://x/{scene}", {"scene": {"nested": 1}}, ["scene"])


def test_build_tool_contract() -> None:
    tool = build_tool(_manifest(side_effects=True))
    assert tool.name == "ha.scene"
    assert tool.side_effects is True and tool.rollback is Rollback.none
    assert tool.preview is not None
    # preview renders the would-call without performing it
    assert "api/scenes/movie" in tool.preview({"scene": "movie"})["would_call"]
