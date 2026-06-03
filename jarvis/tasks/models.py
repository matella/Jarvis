"""Task — a to-do at the boundary (validated + schema-versioned). The table owns the truth."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from jarvis import ids
from jarvis.events.models import utcnow

_MAX_TITLE = 200
_MAX_NOTES = 4000


class TaskStatus(StrEnum):
    open = "open"
    doing = "doing"
    done = "done"
    dropped = "dropped"  # soft-delete — kept for audit


class TaskPriority(StrEnum):
    low = "low"
    normal = "normal"
    high = "high"


class Task(BaseModel):
    id: str = Field(default_factory=lambda: ids.new_id(ids.TASK))
    title: str
    notes: str = ""
    status: TaskStatus = TaskStatus.open
    priority: TaskPriority = TaskPriority.normal
    due_at: datetime | None = None
    completed_at: datetime | None = None
    parent_id: str | None = None
    source_entity_ref: str | None = None  # provenance link, e.g. "mail:<id>"
    schema_version: int = 1
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @property
    def entity_ref(self) -> str:
        return f"task:{self.id}"

    @field_validator("title")
    @classmethod
    def _clean_title(cls, v: str) -> str:
        t = v.strip()[:_MAX_TITLE]
        if not t:
            raise ValueError("task title must be non-empty")
        return t

    @field_validator("notes")
    @classmethod
    def _clean_notes(cls, v: str) -> str:
        return v.strip()[:_MAX_NOTES]
