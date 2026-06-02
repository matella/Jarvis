"""Code-session boundary model — the harness log."""

from __future__ import annotations

import os
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from jarvis import ids
from jarvis.config import get_settings
from jarvis.events.models import utcnow


class CodeStatus(StrEnum):
    running = "running"
    ready = "ready"        # diff captured, awaiting review/apply
    applied = "applied"
    failed = "failed"
    discarded = "discarded"


class CodeSession(BaseModel):
    id: str = Field(default_factory=lambda: ids.new_id(ids.CODESESSION))
    repo_path: str
    base_ref: str = "HEAD"
    worktree_path: str = ""
    task: str
    status: CodeStatus = CodeStatus.running
    diff_text: str = ""
    files_changed: list[str] = Field(default_factory=list)
    log_text: str = ""
    applied: bool = False
    applied_commit: str | None = None
    cost: dict = Field(default_factory=dict)
    schema_version: int = 1
    correlation_id: str = Field(default_factory=lambda: ids.new_id(ids.CORRELATION))
    created_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = None

    @property
    def entity_ref(self) -> str:
        return f"code:{self.id}"


def is_allowed_repo(path: str) -> bool:
    """A repo may be targeted only if it's on the explicit allowlist and is NOT the Jarvis repo.

    Opt-in (empty allowlist → nothing allowed). No-self-modification: the running project's own root
    is refused by default so a coding session can never rewrite Jarvis itself.
    """
    norm = os.path.realpath(path)
    jarvis_root = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if norm == jarvis_root:
        return False
    allowed = {os.path.realpath(p) for p in get_settings().code_repo_allowlist}
    return norm in allowed
