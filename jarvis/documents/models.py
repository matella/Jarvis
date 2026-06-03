"""Document + DocumentVersion — markdown long-form at the boundary (validated + versioned)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from jarvis import ids
from jarvis.events.models import utcnow

_MAX_TITLE = 300
_MAX_BODY = 500_000


class DocStatus(StrEnum):
    draft = "draft"
    final = "final"
    archived = "archived"


class Document(BaseModel):
    id: str = Field(default_factory=lambda: ids.new_id(ids.DOCUMENT))
    title: str
    body_md: str = ""
    status: DocStatus = DocStatus.draft
    source_entity_ref: str | None = None
    schema_version: int = 1
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @property
    def entity_ref(self) -> str:
        return f"document:{self.id}"

    @field_validator("title")
    @classmethod
    def _clean_title(cls, v: str) -> str:
        t = v.strip()[:_MAX_TITLE]
        if not t:
            raise ValueError("document title must be non-empty")
        return t

    @field_validator("body_md")
    @classmethod
    def _trim_body(cls, v: str) -> str:
        return v[:_MAX_BODY]


class DocumentVersion(BaseModel):
    id: str = Field(default_factory=lambda: ids.new_id(ids.DOCVERSION))
    document_id: str
    body_md: str
    author: str = "operator"  # "operator" | "jarvis" | "research"
    summary: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
