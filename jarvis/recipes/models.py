"""Recipe boundary models — validated + schema-versioned. The table owns the truth."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from jarvis import ids
from jarvis.events.models import utcnow

_MAX_TITLE = 200
_MAX_TAGS = 24


class Ingredient(BaseModel):
    name: str
    quantity: str = ""  # free-form ("200", "1/2") — robust to fractions/ranges
    unit: str = ""

    @field_validator("name")
    @classmethod
    def _clean(cls, v: str) -> str:
        n = v.strip()
        if not n:
            raise ValueError("ingredient name must be non-empty")
        return n


class Recipe(BaseModel):
    id: str = Field(default_factory=lambda: ids.new_id(ids.RECIPE))
    title: str
    source_url: str | None = None
    servings: int | None = None
    ingredients: list[Ingredient] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    notes_md: str = ""
    archived: bool = False
    schema_version: int = 1
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @property
    def entity_ref(self) -> str:
        return f"recipe:{self.id}"

    @field_validator("title")
    @classmethod
    def _clean_title(cls, v: str) -> str:
        t = v.strip()[:_MAX_TITLE]
        if not t:
            raise ValueError("recipe title must be non-empty")
        return t

    @field_validator("steps")
    @classmethod
    def _clean_steps(cls, v: list[str]) -> list[str]:
        return [s.strip() for s in v if s.strip()]

    @field_validator("tags")
    @classmethod
    def _norm_tags(cls, v: list[str]) -> list[str]:
        seen: list[str] = []
        for tag in v:
            t = tag.strip().lower()
            if t and t not in seen:
                seen.append(t)
        return seen[:_MAX_TAGS]

    def search_text(self) -> str:
        """Title + ingredients + notes — what the search hook indexes."""
        names = " ".join(i.name for i in self.ingredients)
        return f"{names}\n{self.notes_md}".strip()
