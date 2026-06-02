"""Mail cache boundary models — a mirrored message + its triage verdict."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from jarvis import ids
from jarvis.events.models import utcnow


class Importance(StrEnum):
    low = "low"
    normal = "normal"
    high = "high"


class Triage(BaseModel):
    category: str = "other"  # e.g. personal, work, newsletter, transactional, spam
    importance: Importance = Importance.normal
    needs_reply: bool = False
    summary: str = ""


class CachedMessage(BaseModel):
    id: str = Field(default_factory=lambda: ids.new_id(ids.MAIL))
    account: str
    uid: str
    message_id: str | None = None
    from_addr: str = ""
    to_addrs: list[str] = Field(default_factory=list)
    subject: str = ""
    snippet: str = ""
    body_text: str = ""
    folder: str = "INBOX"
    flags: list[str] = Field(default_factory=list)
    received_at: datetime | None = None
    triage: Triage | None = None
    schema_version: int = 1
    synced_at: datetime = Field(default_factory=utcnow)

    @property
    def entity_ref(self) -> str:
        return f"mail:{self.id}"

    def search_text(self) -> str:
        return f"{self.from_addr} {self.subject}\n{self.snippet or self.body_text[:500]}".strip()
