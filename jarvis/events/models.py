"""Event contract — the append-only source of truth.

`type` is `entity.verb` past-tense (`container.oom_killed`); `severity` is the fixed
five-value set. Two timestamps: `occurred_at` (world time) and `recorded_at` (ingest
time) — never collapsed. Causal identity via `correlation_id` (chain) + `causation_id`
(immediate parent; null for a root event).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from jarvis import ids

_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


def utcnow() -> datetime:
    return datetime.now(UTC)


class Severity(StrEnum):
    debug = "debug"
    info = "info"
    warning = "warning"
    error = "error"
    critical = "critical"


class Event(BaseModel):
    id: str = Field(default_factory=lambda: ids.new_id(ids.EVENT))
    schema_version: int = 1
    type: str
    severity: Severity
    source: str
    entity_ref: str | None = None
    occurred_at: datetime
    recorded_at: datetime = Field(default_factory=utcnow)
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str
    causation_id: str | None = None

    @field_validator("type")
    @classmethod
    def _entity_verb(cls, v: str) -> str:
        if not _TYPE_RE.match(v):
            raise ValueError(f"event type must be 'entity.verb' (lowercase snake), got {v!r}")
        return v
