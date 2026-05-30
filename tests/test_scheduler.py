"""11 unit: scheduler ordering, swap limiter, budgets, and a concurrent priority test."""

from __future__ import annotations

import threading
import time

import pytest

from jarvis.models import scheduler as sched_mod
from jarvis.models.scheduler import (
    BudgetExceeded,
    BudgetLedger,
    InferenceScheduler,
    Priority,
    SwapLimiter,
    _Ticket,
    select,
)


def _t(priority: Priority, seq: int, model: str) -> _Ticket:
    return _Ticket(int(priority), seq, model)


def test_select_prefers_priority_then_fifo() -> None:
    pending = [
        _t(Priority.BACKGROUND, 1, "a"),
        _t(Priority.INTERACTIVE, 2, "a"),
        _t(Priority.INTERACTIVE, 3, "a"),
    ]
    chosen = select(pending, resident="a", swap_blocked=False)
    assert chosen.priority == int(Priority.INTERACTIVE) and chosen.seq == 2  # earliest interactive


def test_select_prefers_resident_when_swaps_blocked() -> None:
    pending = [
        _t(Priority.INTERACTIVE, 1, "other"),  # higher priority but needs a swap
        _t(Priority.BACKGROUND, 2, "resident"),  # lower priority but no swap
    ]
    # swaps capped → avoid the swap, run the resident-model ticket even though it's lower priority
    assert select(pending, resident="resident", swap_blocked=True).model == "resident"
    # swaps available → strict priority wins (the swap is allowed)
    assert select(pending, resident="resident", swap_blocked=False).model == "other"


def test_select_falls_back_when_no_resident_work() -> None:
    pending = [_t(Priority.INTERACTIVE, 1, "other")]
    # capped, but only non-resident work exists → don't stall forever, allow the swap
    assert select(pending, resident="resident", swap_blocked=True).model == "other"


def test_swap_limiter_caps_and_prunes() -> None:
    lim = SwapLimiter(max_per_min=2)
    assert lim.at_cap(now=0.0) is False
    lim.record(0.0)
    lim.record(10.0)
    assert lim.at_cap(now=20.0) is True  # 2 within the minute
    assert lim.at_cap(now=71.0) is False  # the first aged out (>60s)


def test_budget_ledger() -> None:
    ledger = BudgetLedger()
    assert ledger.over("k", 100) is False
    ledger.add("k", 60)
    assert ledger.over("k", 100) is False
    ledger.add("k", 50)
    assert ledger.over("k", 100) is True  # 110 >= 100
    assert ledger.over("k", 0) is False  # 0 limit = unlimited


def test_run_rejects_over_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sched_mod, "_emit_scheduled", lambda *a, **k: None)
    s = InferenceScheduler(max_swaps_per_min=100)
    s.ledger.add("plan:x", 500)
    with pytest.raises(BudgetExceeded):
        s.run("m", Priority.PLAN, lambda: {}, budget_key="plan:x", budget_limit=100)


def test_concurrent_interactive_preempts_background(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sched_mod, "_emit_scheduled", lambda *a, **k: None)
    s = InferenceScheduler(max_swaps_per_min=100)
    order: list[str] = []
    started = threading.Event()
    release = threading.Event()

    def blocker() -> dict:
        started.set()
        release.wait(2)
        order.append("blocker")
        return {}

    def labelled(name: str):
        def fn() -> dict:
            order.append(name)
            return {}
        return fn

    t0 = threading.Thread(target=lambda: s.run("m", Priority.INTERACTIVE, blocker))
    t0.start()
    started.wait(2)  # blocker is now in-flight

    def wait_depth(n: int) -> None:
        for _ in range(200):
            if s.stats()["queue_depth"] >= n:
                return
            time.sleep(0.005)
        raise AssertionError(f"queue never reached depth {n}")

    tb = threading.Thread(target=lambda: s.run("m", Priority.BACKGROUND, labelled("bg")))
    tb.start()
    wait_depth(1)  # background queued behind the blocker
    ti = threading.Thread(target=lambda: s.run("m", Priority.INTERACTIVE, labelled("inter")))
    ti.start()
    wait_depth(2)  # both queued

    release.set()  # let the blocker finish; scheduler now picks among the two queued
    for t in (t0, tb, ti):
        t.join(3)

    # interactive jumped ahead of the earlier-queued background request
    assert order == ["blocker", "inter", "bg"]
