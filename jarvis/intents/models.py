"""Intent + Execution contracts.

An **Intent** is a model proposal; an **Execution** is a deterministic action taken
for it. One Intent → zero-or-more Executions — never flattened. Both carry
`schema_version` and causal identity. `context_ref` on an Intent links to the exact
assembled context + model name/version/params that produced it (the answer to "why?").
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from jarvis import ids
from jarvis.events.models import utcnow


class Risk(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class IntentStatus(StrEnum):
    proposed = "proposed"
    approved = "approved"
    rejected = "rejected"
    executing = "executing"
    executed = "executed"
    failed = "failed"
    cancelled = "cancelled"


class ExecutionOutcome(StrEnum):
    pending = "pending"
    success = "success"
    failure = "failure"
    skipped = "skipped"


class FailureClass(StrEnum):
    permission_denied = "permission_denied"
    timeout = "timeout"
    network_failure = "network_failure"
    resource_exhaustion = "resource_exhaustion"
    validation_failure = "validation_failure"
    tool_unavailable = "tool_unavailable"
    unknown = "unknown"


class IntentReasoning(BaseModel):
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    risk: Risk
    reversible: bool


class Intent(BaseModel):
    intent_id: str = Field(default_factory=lambda: ids.new_id(ids.INTENT))
    schema_version: int = 1
    type: str
    target: dict[str, Any] = Field(default_factory=dict)
    reasoning: IntentReasoning
    requested_by: str
    context_ref: str | None = None
    requires_approval: bool = True
    status: IntentStatus = IntentStatus.proposed
    created_at: datetime = Field(default_factory=utcnow)
    correlation_id: str
    causation_id: str | None = None


class Execution(BaseModel):
    exec_id: str = Field(default_factory=lambda: ids.new_id(ids.EXECUTION))
    schema_version: int = 1
    intent_id: str
    attempt: int = 1
    outcome: ExecutionOutcome = ExecutionOutcome.pending
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None
    error: str | None = None
    failure_class: FailureClass | None = None
    created_at: datetime = Field(default_factory=utcnow)
    correlation_id: str
    causation_id: str | None = None
