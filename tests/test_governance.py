"""Backlog #9 unit: freeze-window logic (pure is_frozen_now)."""

from __future__ import annotations

from datetime import UTC, datetime

from jarvis.core.governance import is_frozen_now


def _at(h: int, m: int = 0) -> datetime:
    return datetime(2026, 5, 30, h, m, tzinfo=UTC)


def test_no_windows_never_frozen() -> None:
    assert is_frozen_now(_at(12), []) is False


def test_simple_window() -> None:
    w = ["09:00-17:00"]
    assert is_frozen_now(_at(8, 59), w) is False
    assert is_frozen_now(_at(9, 0), w) is True
    assert is_frozen_now(_at(16, 59), w) is True
    assert is_frozen_now(_at(17, 0), w) is False  # end is exclusive


def test_window_wrapping_midnight() -> None:
    w = ["22:00-06:00"]  # overnight freeze
    assert is_frozen_now(_at(23), w) is True
    assert is_frozen_now(_at(3), w) is True
    assert is_frozen_now(_at(12), w) is False


def test_multiple_windows_and_bad_entries() -> None:
    w = ["bad", "09:00-10:00", "14:00-15:00"]
    assert is_frozen_now(_at(9, 30), w) is True
    assert is_frozen_now(_at(14, 30), w) is True
    assert is_frozen_now(_at(12), w) is False  # ignores the malformed entry
