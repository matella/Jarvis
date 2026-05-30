"""Plan + step records — the boundary objects for multi-step orchestration.

A Plan is a validated DAG: each PlanStep names ONE known capability (an action intent type, a read
query, or an advisory) plus its target and dependencies. The planner produces it from one
inference; the executor walks it deterministically, updating each step's status/outcome in place.
Versioned + causal like every boundary object.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from jarvis import ids
from jarvis.events.models import utcnow


class StepKind(StrEnum):
    action = "action"  # a capability with side effects → Intent → gate → executor
    read = "read"  # a read-only query against the spine (no gate)
    advisory = "advisory"  # an agent reasoning step (investigate/recommend), no infra change


class StepStatus(StrEnum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    skipped = "skipped"  # dry-run (observe) or not reached
    rolled_back = "rolled_back"


class PlanStatus(StrEnum):
    proposed = "proposed"
    rejected = "rejected"  # a step failed validation (unknown capability)
    running = "running"
    completed = "completed"
    failed = "failed"
    simulated = "simulated"


class PlanStep(BaseModel):
    id: str  # unique within the plan (e.g. "s1"); referenced by depends_on
    kind: StepKind
    capability: str  # intent type, read-query name, or advisory type
    target: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    depends_on: list[str] = Field(default_factory=list)
    status: StepStatus = StepStatus.pending
    outcome: str | None = None
    intent_id: str | None = None
    detail: str | None = None


class Plan(BaseModel):
    plan_id: str = Field(default_factory=lambda: ids.new_id(ids.PLAN))
    schema_version: int = 1
    goal: str
    status: PlanStatus = PlanStatus.proposed
    steps: list[PlanStep] = Field(default_factory=list)
    context_ref: str | None = None
    correlation_id: str
    created_at: datetime = Field(default_factory=utcnow)

    def entities(self) -> set[str]:
        """Distinct entities touched by action steps — the blast-radius surface."""
        out: set[str] = set()
        for step in self.steps:
            if step.kind is StepKind.action:
                t = step.target
                ent = t.get("container") or t.get("entity") or t.get("path")
                if ent:
                    out.add(str(ent))
        return out
