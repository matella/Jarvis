"""Incident contract — a correlated cluster of alerts with an inferred root cause.

Deterministic clustering fills membership (entity_refs, event_ids, severity); the one-shot
correlator model supplies `summary` + `root_cause` (the `IncidentAnalysis` part).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from jarvis import ids
from jarvis.events.models import Severity, utcnow


class IncidentAnalysis(BaseModel):
    """The model's JSON output for one cluster."""

    summary: str
    root_cause: str


class Incident(BaseModel):
    incident_id: str = Field(default_factory=lambda: ids.new_id(ids.INCIDENT))
    schema_version: int = 1
    window_label: str  # e.g. "1h" (column is window_label; 'window' is a SQL reserved word)
    severity: Severity
    summary: str
    root_cause: str | None = None
    entity_refs: list[str] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list)
    event_count: int = 0
    context_ref: str | None = None
    correlation_id: str
    created_at: datetime = Field(default_factory=utcnow)
