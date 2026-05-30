"""Action-safety policies — limits and approval rules that compose with the mode gate.

The operational mode (core/modes.py) decides the baseline (observe/approval/semi_auto/maintenance).
Policies add orthogonal guardrails the orchestrator must respect before a multi-step plan runs:
- **blast radius** — a single plan may touch at most K distinct entities (a typo'd "restart all"
  can't cascade);
- **rate limit** — at most N real executions per rolling window across the whole system;
- **approval policy** — declarative auto-approve rules (by capability/max-risk) that can widen
  semi_autonomous, never narrow the mode's own floor.

All pure/queryable so they're unit-testable and enforced deterministically (never by the model).
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg

from jarvis.config import get_settings
from jarvis.intents.models import Intent, Risk

_RISK_ORDER = {Risk.low: 0, Risk.medium: 1, Risk.high: 2}


class BlastRadiusExceeded(Exception):
    """A plan would touch more distinct entities than policy permits."""


class RateLimitExceeded(Exception):
    """Too many real executions within the configured window."""


def check_blast_radius(entities: set[str], *, max_entities: int | None = None) -> None:
    limit = max_entities if max_entities is not None else get_settings().plan_max_entities
    if len(entities) > limit:
        raise BlastRadiusExceeded(
            f"plan touches {len(entities)} entities (limit {limit}): {sorted(entities)}"
        )


def count_recent_actions(conn: psycopg.Connection, *, window_s: int) -> int:
    """Real (non-skipped) executions in the recent window — the rate-limit numerator."""
    row = conn.execute(
        "SELECT count(*) AS n FROM executions "
        "WHERE created_at >= now() - make_interval(secs => %s) "
        "AND outcome IN ('success', 'failure')",
        (window_s,),
    ).fetchone()
    return int(row["n"]) if row else 0


def check_rate_limit(conn: psycopg.Connection, *, planned_actions: int = 1) -> None:
    s = get_settings()
    recent = count_recent_actions(conn, window_s=s.action_rate_window_s)
    if recent + planned_actions > s.action_rate_limit:
        raise RateLimitExceeded(
            f"{recent} actions in last {s.action_rate_window_s}s + {planned_actions} planned "
            f"exceeds limit {s.action_rate_limit}"
        )


@dataclass(frozen=True)
class ApprovalRule:
    """Auto-approve any intent of `capability` (exact type) up to `max_risk` inclusive."""

    capability: str
    max_risk: Risk = Risk.low


@dataclass(frozen=True)
class ApprovalPolicy:
    rules: tuple[ApprovalRule, ...] = ()

    def auto_approvable(self, intent: Intent) -> bool:
        """True iff a rule explicitly permits auto-approving this intent. Default-deny."""
        for rule in self.rules:
            if rule.capability == intent.type and (
                _RISK_ORDER[intent.reasoning.risk] <= _RISK_ORDER[rule.max_risk]
            ):
                return True
        return False


# The active policy. Empty by default — semi_autonomous's own low-risk+reversible rule still
# applies; this only *widens* it when an operator adds rules. Wired from config/CLI later.
_POLICY = ApprovalPolicy()


def get_policy() -> ApprovalPolicy:
    return _POLICY
