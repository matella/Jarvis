"""Model cookbook — pref validation, presets, backend_for resolution + safety. No DB."""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from jarvis.cookbook import api
from jarvis.cookbook.models import PRESETS, ModelPref, PrefScope


def test_pref_validates_backend() -> None:
    ModelPref(scope_key="research.synthesize", backend="claude")
    with pytest.raises(ValueError):
        ModelPref(scope_key="x", backend="gpt-9")


def test_presets_cover_the_known_actions() -> None:
    assert set(PRESETS) == {"quality", "frugal", "balanced"}
    assert PRESETS["quality"]["research.synthesize"] == "claude"
    assert all(b == "local" for b in PRESETS["frugal"].values())
    assert PRESETS["balanced"]["research.synthesize"] == "claude"
    assert PRESETS["balanced"]["document.ai_edit"] == "local"


def test_backend_for_returns_pref_or_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "jarvis.cookbook.repository.get_action_pref",
        lambda conn, key: ModelPref(scope_key=key, backend="claude") if key == "x" else None,
    )
    assert api.backend_for(object(), "x") == "claude"
    assert api.backend_for(object(), "y", default="local") == "local"
    assert api.backend_for(object(), "y") is None


def test_backend_for_action_is_best_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    # A DB failure must fall back to the caller's default — never break the inference it informs.
    @contextmanager
    def _boom():
        raise RuntimeError("db down")
        yield  # pragma: no cover

    monkeypatch.setattr("jarvis.db.connect", _boom)
    assert api.backend_for_action("postmortem", default="claude") == "claude"


def test_scope_enum_values() -> None:
    assert PrefScope.action.value == "action" and PrefScope.global_.value == "global"
