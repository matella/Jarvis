"""Claude availability + a rate-limit circuit breaker + a soft daily call budget.

The breaker and budget take an injected clock (`now=`), mirroring `scheduler.SwapLimiter`, so they
are pure and unit-testable. `claude_available()` caches a cheap PATH+token probe so it isn't run on
every call. All process-global instances live in `scheduler` (these are the reusable mechanisms).
"""

from __future__ import annotations

import datetime as _dt
import shutil
import time


class CircuitBreaker:
    """Tripped by a rate-limit; forces `local` until the cooldown elapses, then auto-closes."""

    def __init__(self, *, cooldown_s: int) -> None:
        self._cooldown = cooldown_s
        self._opened_at: float | None = None

    def record_rate_limit(self, *, now: float) -> None:
        self._opened_at = now

    def is_open(self, *, now: float) -> bool:
        return self._opened_at is not None and (now - self._opened_at) < self._cooldown


class DailyBudget:
    """Soft per-UTC-day cap on Claude calls — a runaway routine can't drain the subscription."""

    def __init__(self, *, limit: int) -> None:
        self._limit = limit
        self._day = ""
        self._count = 0

    @staticmethod
    def _utc_day(now: float) -> str:
        return _dt.datetime.fromtimestamp(now, _dt.UTC).strftime("%Y-%m-%d")

    def record(self, *, now: float) -> None:
        day = self._utc_day(now)
        if day != self._day:
            self._day, self._count = day, 0
        self._count += 1

    def exhausted(self, *, now: float) -> bool:
        return self._utc_day(now) == self._day and self._count >= self._limit


_avail_cache: tuple[float, bool] = (0.0, False)


def claude_available() -> bool:
    """True iff the `claude` CLI is on PATH AND CLAUDE_CODE_OAUTH_TOKEN is set. Cached (TTL)."""
    global _avail_cache
    from jarvis.config import get_settings
    from jarvis.security.secrets import get_provider

    now = time.monotonic()
    ts, val = _avail_cache
    if now - ts < get_settings().claude_availability_cache_ttl:
        return val
    ok = shutil.which("claude") is not None and bool(get_provider().get("CLAUDE_CODE_OAUTH_TOKEN"))
    _avail_cache = (now, ok)
    return ok
