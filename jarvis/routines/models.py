"""Routine records — schedule + action, both small typed specs.

Schedules are deliberately simple (daily-at / interval) rather than a full cron grammar — enough for
"morning briefing" and "hourly check" without a parser. Actions name an existing capability so a
routine can never do anything the gate wouldn't allow.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from jarvis import ids
from jarvis.events.models import utcnow


class ScheduleKind(StrEnum):
    daily = "daily"  # {"kind":"daily","at":"07:30"}
    interval = "interval"  # {"kind":"interval","seconds":3600}


class ActionKind(StrEnum):
    summary = "summary"  # {"kind":"summary","hours":12}
    briefing = "briefing"  # {"kind":"briefing","hours":12} — incidents + critical + summary
    search = "search"  # {"kind":"search","query":"..."}
    day_brief = "day_brief"  # calendar + tasks due + important mail + research + homelab health
    news_brief = "news_brief"  # synthesize the day's top-N world-news stories + push


class Schedule(BaseModel):
    kind: ScheduleKind
    at: str = "07:30"  # HH:MM for daily
    seconds: int = 3600  # for interval


class Action(BaseModel):
    kind: ActionKind
    hours: int = 12
    query: str = ""


class Routine(BaseModel):
    id: str = Field(default_factory=lambda: ids.new_id(ids.ROUTINE))
    name: str
    schedule: Schedule
    action: Action
    enabled: bool = True
    last_run: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)

    def as_row(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name,
            "schedule": self.schedule.model_dump(mode="json"),
            "action": self.action.model_dump(mode="json"),
            "enabled": self.enabled, "last_run": self.last_run, "created_at": self.created_at,
        }
