"""GPU scheduler — a priority queue in front of the one resident model.

DECISIONS deferred this until contention existed; chat + plans + reactor + connectors now compete
for the single 8 GB card. This generalizes the bare `Semaphore(1)`: still exactly one inference
in-flight, but requests are ordered by priority (interactive chat/voice > plan steps > background
summaries/reactor), with a swap-frequency limiter (bias toward the resident model so we don't
thrash) and optional per-key token budgets (a runaway routine can't starve the GPU).

The selection, swap limiter, and budget ledger are pure and unit-tested; `InferenceScheduler.run`
is the thin concurrent shell. The router keeps role→tag + one-resident + model.* events; the
scheduler owns ordering and emits `inference.scheduled` with wait-time + queue-depth.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import IntEnum

from jarvis import ids
from jarvis.config import get_settings
from jarvis.models.backends.availability import CircuitBreaker, DailyBudget

# Process-global breaker + soft daily budget for the off-GPU claude backend (config-fixed at load).
_breaker = CircuitBreaker(cooldown_s=get_settings().claude_breaker_cooldown_s)
_budget = DailyBudget(limit=get_settings().claude_daily_call_budget)
_last_fallback_notify = 0.0


def _emit(event) -> None:  # single emit point so tests can collect events
    from jarvis.events.stream import emit_event

    emit_event(event)


def _emit_inference_completed(model: str, backend: str, cid: str, ctx, started: float) -> None:
    from jarvis.events.models import Event, Severity, utcnow

    _emit(Event(
        type="inference.completed", severity=Severity.info, source="scheduler",
        entity_ref=f"model:{model}", occurred_at=utcnow(),
        payload={"model": model, "backend": backend, "context_ref": ctx,
                 "duration_ms": round((time.monotonic() - started) * 1000, 1)},
        correlation_id=cid,
    ))


def _emit_fallback(cid: str, failure: str, reason: str) -> None:
    from jarvis.events.models import Event, Severity, utcnow

    _emit(Event(
        type="llm.fallback", severity=Severity.warning, source="scheduler",
        entity_ref="backend:claude", occurred_at=utcnow(),
        payload={"intended_backend": "claude", "failure_class": failure, "reason": reason,
                 "correlation_id": cid},
        correlation_id=cid,
    ))


def _notify_fallback(failure: str) -> None:
    global _last_fallback_notify
    now = time.monotonic()
    if now - _last_fallback_notify < get_settings().notify_cooldown_s:
        return  # debounce: one notice per cooldown window
    _last_fallback_notify = now
    from jarvis.notify.channel import send

    send(title="Jarvis — Claude backend unavailable",
         message=f"Falling back to local reasoning ({failure}).", priority="default")


class Priority(IntEnum):
    # Lower value = scheduled first (min-ordering).
    INTERACTIVE = 0  # chat / voice — a human is waiting
    PLAN = 1  # plan steps
    BACKGROUND = 2  # reactor, summaries, correlation, embeddings


class BudgetExceeded(Exception):
    """A budget key has consumed its token allowance; new requests are rejected."""


@dataclass(order=True)
class _Ticket:
    priority: int
    seq: int
    model: str = field(compare=False)


class SwapLimiter:
    """Caps model swaps per rolling minute. Pure given an injected clock."""

    def __init__(self, max_per_min: int) -> None:
        self.max_per_min = max_per_min
        self._stamps: list[float] = []

    def _prune(self, now: float) -> None:
        self._stamps = [t for t in self._stamps if now - t < 60.0]

    def at_cap(self, now: float) -> bool:
        self._prune(now)
        return len(self._stamps) >= self.max_per_min

    def record(self, now: float) -> None:
        self._prune(now)
        self._stamps.append(now)


class BudgetLedger:
    """Tracks tokens consumed per key (session/plan/routine). Thread-safe."""

    def __init__(self) -> None:
        self._used: dict[str, int] = {}
        self._lock = threading.Lock()

    def over(self, key: str, limit: int) -> bool:
        if not key or not limit:
            return False
        with self._lock:
            return self._used.get(key, 0) >= limit

    def add(self, key: str, tokens: int) -> None:
        if not key or not tokens:
            return
        with self._lock:
            self._used[key] = self._used.get(key, 0) + tokens

    def used(self, key: str) -> int:
        with self._lock:
            return self._used.get(key, 0)


def select(pending: list[_Ticket], resident: str | None, *, swap_blocked: bool) -> _Ticket:
    """Pick the next ticket: highest priority, but prefer the resident model when swaps are capped.

    Pure: given the current pending list, the resident model, and whether the swap limiter is at its
    cap, choose deterministically. When swaps are blocked we only consider resident-model tickets if
    any exist (avoids a swap); otherwise we fall back to all (never stall forever).
    """
    pool = pending
    if swap_blocked and resident is not None:
        resident_pool = [t for t in pending if t.model == resident]
        if resident_pool:
            pool = resident_pool
    return min(pool, key=lambda t: (t.priority, t.seq))


def _tokens_of(result: dict) -> int:
    return int(result.get("prompt_eval_count") or 0) + int(result.get("eval_count") or 0)


class InferenceScheduler:
    def __init__(self, *, max_swaps_per_min: int | None = None) -> None:
        cap = (
            max_swaps_per_min if max_swaps_per_min is not None
            else get_settings().sched_max_swaps_per_min
        )
        self._cond = threading.Condition()
        self._pending: list[_Ticket] = []
        self._in_flight = False
        self._resident: str | None = None
        self._seq = 0
        self._swaps = SwapLimiter(cap)
        self.ledger = BudgetLedger()
        self._now = _monotonic  # injectable for tests

    def run(
        self, model: str, priority: Priority, fn: Callable[[], dict], *,
        budget_key: str = "", budget_limit: int = 0,
    ) -> dict:
        """Schedule one inference. Blocks until selected, runs `fn`, returns its result dict."""
        if budget_key and budget_limit and self.ledger.over(budget_key, budget_limit):
            raise BudgetExceeded(
                f"budget {budget_key!r} exhausted ({self.ledger.used(budget_key)}/{budget_limit})"
            )
        with self._cond:
            self._seq += 1
            ticket = _Ticket(int(priority), self._seq, model)
            self._pending.append(ticket)
            queued_at = self._now()
            depth = len(self._pending)
            while self._in_flight or select(
                self._pending, self._resident, swap_blocked=self._swaps.at_cap(self._now())
            ) is not ticket:
                self._cond.wait()
            self._pending.remove(ticket)
            self._in_flight = True
            causes_swap = self._resident is not None and self._resident != model
            wait_ms = round((self._now() - queued_at) * 1000, 1)

        _emit_scheduled(model, priority, wait_ms, depth)
        try:
            result = fn()
        finally:
            with self._cond:
                now = self._now()
                if causes_swap or self._resident is None:
                    self._swaps.record(now)
                self._resident = model
                self._in_flight = False
                self._cond.notify_all()
        if budget_key:
            self.ledger.add(budget_key, _tokens_of(result))
        return result

    def stats(self) -> dict:
        with self._cond:
            return {"queue_depth": len(self._pending), "in_flight": self._in_flight,
                    "resident": self._resident}


def _monotonic() -> float:
    import time

    return time.monotonic()


def _emit_scheduled(model: str, priority: Priority, wait_ms: float, depth: int) -> None:
    try:
        from jarvis.events.models import Event, Severity, utcnow
        from jarvis.events.stream import emit_event

        emit_event(Event(
            type="inference.scheduled", severity=Severity.debug, source="scheduler",
            entity_ref=f"model:{model}", occurred_at=utcnow(),
            payload={"model": model, "priority": priority.name.lower(),
                     "wait_ms": wait_ms, "queue_depth": depth},
            correlation_id=ids.new_id(ids.CORRELATION),
        ))
    except Exception:  # noqa: BLE001 — telemetry must never break scheduling
        pass


_SCHEDULER = InferenceScheduler()


def get_scheduler() -> InferenceScheduler:
    return _SCHEDULER


class _SchemaMiss(Exception):
    """Claude returned content that doesn't satisfy the requested JSON schema."""


def _validate_schema(content: str, fmt: dict | str) -> None:
    """Lightweight check (no jsonschema dep): must be a JSON object with all `required` keys."""
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError) as exc:
        raise _SchemaMiss(f"not JSON: {exc}") from exc
    required = fmt.get("required", []) if isinstance(fmt, dict) else []
    if not isinstance(data, dict) or any(k not in data for k in required):
        raise _SchemaMiss(f"missing required keys {required}")


def _resolve_backend(*, explicit: str | None, priority: Priority, has_schema: bool) -> str:
    from jarvis.models.backends.resolve import resolve_backend
    from jarvis.models.backends.state import cached_default_backend

    # The global `jarvis model` default applies to INTERACTIVE chat only; background work stays
    # local unless a caller explicitly asks for claude (so reactor/anomaly/triage never drift up).
    global_default = cached_default_backend() if priority == Priority.INTERACTIVE else None
    return resolve_backend(
        explicit, None, global_default, has_schema=has_schema,  # type: ignore[arg-type]
        breaker_open=_breaker.is_open(now=time.monotonic()),
        budget_exhausted=_budget.exhausted(now=time.time()),
    )


def _run_local(role, messages, priority, budget_key, budget_limit, kwargs) -> dict:
    from jarvis.models import router
    from jarvis.models.router import model_for_role

    model = model_for_role(role)
    return get_scheduler().run(
        model, priority, lambda: router.chat(role, messages, **kwargs),
        budget_key=budget_key, budget_limit=budget_limit,
    )


def _run_claude(role, messages, fmt, priority, budget_key, budget_limit, kwargs) -> dict:
    from jarvis.models.backends import claude as claude_mod
    from jarvis.models.router import _with_persona

    s = get_settings()
    cid = kwargs.get("correlation_id") or ids.new_id(ids.CORRELATION)
    ctx = kwargs.get("context_ref")
    started = time.monotonic()
    try:
        # Prepend the Jarvis identity (as the local path does) so Claude answers AS Jarvis, not its
        # own default "Claude Code" persona. claude.py strips the tool-only sections from it.
        resp = claude_mod.claude_backend(
            role, _with_persona(messages), fmt=fmt, timeout=s.claude_call_timeout
        )
        if fmt is not None:
            _validate_schema(resp["message"]["content"], fmt)  # raises _SchemaMiss on a miss
        _budget.record(now=time.time())
        _emit_inference_completed(resp.get("model", "claude"), "claude", cid, ctx, started)
        return resp
    except (claude_mod.ClaudeBackendError, _SchemaMiss) as exc:
        failure = getattr(exc, "failure_class", "validation_failure")
        if failure == "resource_exhaustion":
            _breaker.record_rate_limit(now=time.monotonic())
        _emit_fallback(cid, failure, str(exc)[:200])
        _notify_fallback(failure)
        local = _run_local(role, messages, priority, budget_key, budget_limit, kwargs)
        local["backend_used"] = "local"
        local["error"] = f"claude {failure}"
        return local


def chat(role: str, messages: list[dict], *, priority: Priority = Priority.BACKGROUND,
         backend: str | None = None, budget_key: str = "", budget_limit: int = 0, **kwargs) -> dict:
    """Scheduled wrapper + backend dispatch. `local` → the GPU scheduler (unchanged); `claude` →
    off-GPU `claude -p`, bypassing the semaphore, schema-validate-then-fallback to local."""
    fmt = kwargs.get("format")
    chosen = _resolve_backend(explicit=backend, priority=priority, has_schema=fmt is not None)
    if chosen == "local":
        return _run_local(role, messages, priority, budget_key, budget_limit, kwargs)
    return _run_claude(role, messages, fmt, priority, budget_key, budget_limit, kwargs)
