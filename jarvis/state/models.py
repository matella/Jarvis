"""State projection model.

`state` is a **projection** of the event log — only the projector writes it. This model
lands in M2 (with its only writer), deferred from M1 on purpose. It is a derived view, not
a boundary object, so it carries no `schema_version`/causal ids.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from jarvis.events.models import utcnow


class StateRow(BaseModel):
    entity: str
    kind: str
    status: str | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=utcnow)
    last_event_id: str | None = None
