"""7 unit: action-safety policies — blast radius, rate limit, approval rules."""

from __future__ import annotations

import pytest

from jarvis.core import policies
from jarvis.core.policies import (
    ApprovalPolicy,
    ApprovalRule,
    BlastRadiusExceeded,
    RateLimitExceeded,
    check_blast_radius,
    check_rate_limit,
)
from jarvis.intents.models import Intent, IntentReasoning, Risk


def test_blast_radius_within_limit() -> None:
    check_blast_radius({"a", "b"}, max_entities=3)  # no raise


def test_blast_radius_exceeded() -> None:
    with pytest.raises(BlastRadiusExceeded, match="limit 2"):
        check_blast_radius({"a", "b", "c"}, max_entities=2)


class _Cfg:
    action_rate_limit = 5
    action_rate_window_s = 300


class _Conn:
    def __init__(self, recent: int) -> None:
        self._recent = recent

    def execute(self, *_a, **_k):
        recent = self._recent
        class _Cur:
            def fetchone(self_inner):
                return {"n": recent}
        return _Cur()


def test_rate_limit_allows_under_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(policies, "get_settings", lambda: _Cfg())
    check_rate_limit(_Conn(3), planned_actions=2)  # 3 + 2 == 5, at the cap, allowed


def test_rate_limit_blocks_over_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(policies, "get_settings", lambda: _Cfg())
    with pytest.raises(RateLimitExceeded):
        check_rate_limit(_Conn(4), planned_actions=2)  # 4 + 2 == 6 > 5


def _intent(cap: str, risk: Risk) -> Intent:
    return Intent(
        type=cap, target={}, requested_by="t", correlation_id="corr_x",
        reasoning=IntentReasoning(summary="s", confidence=0.5, risk=risk, reversible=True),
    )


def test_approval_policy_default_denies() -> None:
    policy = ApprovalPolicy()
    assert policy.auto_approvable(_intent("docker.restart_container", Risk.low)) is False


def test_approval_policy_rule_matches_capability_and_risk() -> None:
    policy = ApprovalPolicy(rules=(ApprovalRule("docker.restart_container", Risk.medium),))
    assert policy.auto_approvable(_intent("docker.restart_container", Risk.low)) is True
    assert policy.auto_approvable(_intent("docker.restart_container", Risk.medium)) is True
    # higher risk than the rule allows → not auto-approved
    assert policy.auto_approvable(_intent("docker.restart_container", Risk.high)) is False
    # different capability → no match
    assert policy.auto_approvable(_intent("code.edit_file", Risk.low)) is False
