"""Circuit breaker + daily budget unit tests (injected clock) + cached availability gating."""

from __future__ import annotations

from jarvis.models.backends.availability import CircuitBreaker, DailyBudget


def test_breaker_opens_then_auto_closes() -> None:
    b = CircuitBreaker(cooldown_s=900)
    assert b.is_open(now=1000.0) is False
    b.record_rate_limit(now=1000.0)
    assert b.is_open(now=1100.0) is True    # within cooldown
    assert b.is_open(now=1901.0) is False   # elapsed → auto-close


def test_daily_budget_caps_and_rolls_over() -> None:
    bud = DailyBudget(limit=2)
    day = 1_700_000_000.0
    bud.record(now=day)
    bud.record(now=day)
    assert bud.exhausted(now=day) is True
    assert bud.exhausted(now=day + 86_400) is False  # next UTC day resets the counter


def test_claude_available_gated_by_token(monkeypatch) -> None:
    import jarvis.models.backends.availability as av

    av._avail_cache = (0.0, False)  # bust cache
    monkeypatch.setattr(av.shutil, "which", lambda _: "/usr/bin/claude")
    # token absent → unavailable even with the CLI present
    monkeypatch.setattr("jarvis.security.secrets.get_provider",
                        lambda: type("P", (), {"get": lambda self, k: None})())
    assert av.claude_available() is False
