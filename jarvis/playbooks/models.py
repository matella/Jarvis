"""Playbook contract — operator-authored procedural memory.

A known fix/procedure: `title` + `when_to_use` (the matching basis) + `procedure` (the steps).
The embedding is a stored retrieval index (computed from title+when_to_use), not a domain field.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from jarvis import ids
from jarvis.events.models import utcnow


class Playbook(BaseModel):
    id: str = Field(default_factory=lambda: ids.new_id(ids.PLAYBOOK))
    title: str
    when_to_use: str = ""
    procedure: str
    created_at: datetime = Field(default_factory=utcnow)
