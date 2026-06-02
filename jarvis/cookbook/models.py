"""Model-pref boundary model + the named presets."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from jarvis import ids
from jarvis.events.models import utcnow


class PrefScope(StrEnum):
    action = "action"
    routine = "routine"
    global_ = "global"


class ModelPref(BaseModel):
    id: str = Field(default_factory=lambda: ids.new_id(ids.MODELPREF))
    scope: PrefScope = PrefScope.action
    scope_key: str  # action name (e.g. "research.synthesize") / routine id / "" for global
    backend: str  # "local" | "claude"
    model: str = ""  # reserved for a future model_hint→model map
    params: dict = Field(default_factory=dict)
    preset_name: str | None = None
    schema_version: int = 1
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @field_validator("backend")
    @classmethod
    def _valid_backend(cls, v: str) -> str:
        if v not in ("local", "claude"):
            raise ValueError(f"backend must be 'local' or 'claude', got {v!r}")
        return v


# Named presets — applying one writes a batch of per-action rows. The cookbook's "recipes".
# Keys are action identifiers callers pass to `backend_for_action`.
PRESETS: dict[str, dict[str, str]] = {
    # Quality: spend Claude where prose/reasoning quality shows; cheap frequent work stays local.
    "quality": {
        "research.synthesize": "claude",
        "document.ai_edit": "claude",
        "mail.draft": "claude",
        "postmortem": "claude",
        "conversation.compose": "claude",
    },
    # Frugal: everything local (no subscription spend).
    "frugal": {
        "research.synthesize": "local",
        "document.ai_edit": "local",
        "mail.draft": "local",
        "postmortem": "local",
        "conversation.compose": "local",
    },
    # Balanced: Claude only for the heaviest synthesis.
    "balanced": {
        "research.synthesize": "claude",
        "document.ai_edit": "local",
        "mail.draft": "local",
        "postmortem": "claude",
        "conversation.compose": "local",
    },
}
