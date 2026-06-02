"""Note — a markdown jotting at the boundary (validated + schema-versioned)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from jarvis import ids
from jarvis.events.models import utcnow

_MAX_TITLE = 200
_MAX_BODY = 100_000
_MAX_TAGS = 24


class Note(BaseModel):
    id: str = Field(default_factory=lambda: ids.new_id(ids.NOTE))
    title: str = ""
    body_md: str = ""
    pinned: bool = False
    archived: bool = False
    tags: list[str] = Field(default_factory=list)
    source_entity_ref: str | None = None
    schema_version: int = 1
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @property
    def entity_ref(self) -> str:
        return f"note:{self.id}"

    @field_validator("body_md")
    @classmethod
    def _trim_body(cls, v: str) -> str:
        return v.strip()[:_MAX_BODY]

    @field_validator("tags")
    @classmethod
    def _norm_tags(cls, v: list[str]) -> list[str]:
        seen: list[str] = []
        for tag in v:
            t = tag.strip().lower()
            if t and t not in seen:
                seen.append(t)
        return seen[:_MAX_TAGS]

    @model_validator(mode="after")
    def _derive_title(self) -> Note:
        # Title defaults to the first non-empty line of the body (markdown heading marks stripped).
        if not self.title.strip():
            for line in self.body_md.splitlines():
                stripped = line.lstrip("# ").strip()
                if stripped:
                    object.__setattr__(self, "title", stripped[:_MAX_TITLE])
                    break
        else:
            object.__setattr__(self, "title", self.title.strip()[:_MAX_TITLE])
        if not self.title and not self.body_md:
            raise ValueError("a note needs a title or a body")
        return self
