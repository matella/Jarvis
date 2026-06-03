"""Calendar event boundary model — validated + schema-versioned."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

from jarvis import ids
from jarvis.events.models import utcnow

_MAX_TITLE = 300


class EventSource(StrEnum):
    local = "local"   # the source of truth (operator/Jarvis author it)
    google = "google"  # read-mirror
    ics = "ics"        # read-mirror


class EventStatus(StrEnum):
    confirmed = "confirmed"
    tentative = "tentative"
    cancelled = "cancelled"


class CalendarEvent(BaseModel):
    id: str = Field(default_factory=lambda: ids.new_id(ids.CALEVENT))
    source: EventSource = EventSource.local
    external_uid: str | None = None  # mirror dedupe key (None for local)
    title: str
    location: str = ""
    description: str = ""
    starts_at: datetime
    ends_at: datetime | None = None
    all_day: bool = False
    rrule: str | None = None
    status: EventStatus = EventStatus.confirmed
    source_entity_ref: str | None = None  # provenance, e.g. "mail:<id>"
    schema_version: int = 1
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    synced_at: datetime | None = None

    @property
    def entity_ref(self) -> str:
        return f"calendar:{self.id}"

    @property
    def is_mirror(self) -> bool:
        return self.source is not EventSource.local

    @field_validator("title")
    @classmethod
    def _clean_title(cls, v: str) -> str:
        t = v.strip()[:_MAX_TITLE]
        if not t:
            raise ValueError("event title must be non-empty")
        return t

    @model_validator(mode="after")
    def _check_window(self) -> CalendarEvent:
        if self.ends_at is not None and self.ends_at < self.starts_at:
            raise ValueError("event ends_at is before starts_at")
        return self

    def search_text(self) -> str:
        return f"{self.location}\n{self.description}".strip()
