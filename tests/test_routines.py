"""Cross-cutting A unit: routine scheduling decisions (pure is_due)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jarvis.routines.models import Schedule
from jarvis.routines.scheduler import is_due

UTC = UTC


def _at(h: int, m: int = 0) -> datetime:
    return datetime(2026, 5, 30, h, m, tzinfo=UTC)


def test_interval_due_when_never_run() -> None:
    s = Schedule(kind="interval", seconds=3600)
    assert is_due(s, _at(8), last_run=None) is True


def test_interval_not_due_before_window() -> None:
    s = Schedule(kind="interval", seconds=3600)
    assert is_due(s, _at(8, 30), last_run=_at(8)) is False  # only 30m elapsed
    assert is_due(s, _at(9), last_run=_at(8)) is True  # 60m elapsed


def test_daily_due_after_target_and_not_run_today() -> None:
    s = Schedule(kind="daily", at="07:30")
    assert is_due(s, _at(7, 0), last_run=None) is False  # before target
    assert is_due(s, _at(8, 0), last_run=None) is True  # after target, never run
    assert is_due(s, _at(8, 0), last_run=_at(7, 45)) is False  # already ran past target today


def test_daily_due_again_next_day() -> None:
    s = Schedule(kind="daily", at="07:30")
    yesterday = _at(7, 45) - timedelta(days=1)
    assert is_due(s, _at(8, 0), last_run=yesterday) is True  # last run was yesterday


def test_daily_bad_time_never_due() -> None:
    assert is_due(Schedule(kind="daily", at="nope"), _at(8), last_run=None) is False
