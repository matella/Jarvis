"""Graduated gate (Evolution #2) — the auto-run vs gated truth table. No DB/LLM."""

from __future__ import annotations

from jarvis.intents.models import Risk
from jarvis.tools.grading import grade


def test_personal_data_crud_auto_runs() -> None:
    # low-risk + reversible + no side effects + on-box → auto-run (note/task/recipe/doc CRUD)
    g = grade(side_effects=False, reversible=True, risk=Risk.low)
    assert g.auto_run is True and g.requires_approval is False


def test_side_effecting_action_is_gated() -> None:
    # send email / restart container — side effects → gated
    g = grade(side_effects=True, reversible=False, risk=Risk.medium)
    assert g.requires_approval is True and g.auto_run is False


def test_external_with_no_box_side_effects_is_gated() -> None:
    # research.run touches the web (external) though it has no on-box side effect → gated
    g = grade(side_effects=False, reversible=True, risk=Risk.low, external=True)
    assert g.requires_approval is True


def test_irreversible_is_gated_even_if_low_risk_on_box() -> None:
    g = grade(side_effects=False, reversible=False, risk=Risk.low)
    assert g.requires_approval is True


def test_higher_risk_is_gated_even_if_reversible() -> None:
    g = grade(side_effects=False, reversible=True, risk=Risk.high)
    assert g.requires_approval is True
    assert grade(side_effects=False, reversible=True, risk=Risk.medium).requires_approval is True


def test_gate_carries_risk_and_reversible_through() -> None:
    g = grade(side_effects=False, reversible=True, risk=Risk.low)
    assert g.risk is Risk.low and g.reversible is True
