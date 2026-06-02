"""Pure backend-resolution unit tests — precedence + hard overrides."""

from __future__ import annotations

from jarvis.models.backends.resolve import resolve_backend as r


def _kw(**over):
    base = dict(has_schema=False, breaker_open=False, budget_exhausted=False)
    base.update(over)
    return base


def test_precedence() -> None:
    assert r("claude", None, "local", **_kw()) == "claude"      # explicit wins
    assert r(None, "claude", "local", **_kw()) == "claude"      # routine over global
    assert r(None, None, "claude", **_kw()) == "claude"         # global
    assert r(None, None, None, **_kw()) == "local"              # default


def test_hard_overrides_force_local() -> None:
    assert r("claude", None, "claude", **_kw(breaker_open=True)) == "local"
    assert r("claude", None, "claude", **_kw(budget_exhausted=True)) == "local"


def test_schema_forces_local_unless_explicit_claude() -> None:
    assert r(None, None, "claude", **_kw(has_schema=True)) == "local"   # from default → local
    assert r(None, "claude", None, **_kw(has_schema=True)) == "local"   # from routine → local
    assert r("claude", None, None, **_kw(has_schema=True)) == "claude"  # deliberate → kept
