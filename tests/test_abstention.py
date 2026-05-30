"""Backlog #4 unit: confidence-based abstention decision (pure)."""

from __future__ import annotations

from jarvis.agents.conversation import should_abstain


def test_abstains_below_floor() -> None:
    assert should_abstain(0.30, floor=0.45) is True
    assert should_abstain(0.44, floor=0.45) is True


def test_acts_at_or_above_floor() -> None:
    assert should_abstain(0.45, floor=0.45) is False
    assert should_abstain(0.90, floor=0.45) is False
