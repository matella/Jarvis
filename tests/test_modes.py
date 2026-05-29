"""Operational-mode policy unit tests — the decide() matrix. No DB."""

from jarvis.core.modes import Decision, Mode, decide
from jarvis.intents.models import Intent, IntentReasoning


def _intent(risk: str, reversible: bool) -> Intent:
    return Intent(
        type="docker.restart_container", target={"container": "x"},
        reasoning=IntentReasoning(summary="s", confidence=0.9, risk=risk, reversible=reversible),
        requested_by="agent", correlation_id="corr_x",
    )


def test_observe_is_dry_run() -> None:
    assert decide(Mode.observe, _intent("low", True)) == Decision(dry_run=True)


def test_maintenance_blocks() -> None:
    assert decide(Mode.maintenance, _intent("low", True)) == Decision(blocked=True)


def test_approval_required_forces_approval() -> None:
    # even a low-risk reversible intent needs explicit approval under approval_required
    assert decide(Mode.approval_required, _intent("low", True)) == Decision(force_approval=True)


def test_semi_autonomous_auto_approves_low_risk_reversible() -> None:
    assert decide(Mode.semi_autonomous, _intent("low", True)) == Decision(auto_approve=True)


def test_semi_autonomous_holds_high_or_irreversible() -> None:
    assert decide(Mode.semi_autonomous, _intent("high", True)) == Decision(force_approval=True)
    assert decide(Mode.semi_autonomous, _intent("low", False)) == Decision(force_approval=True)
