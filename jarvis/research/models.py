"""Deep-research boundary models — the run record (harness log) + its depth caps."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from jarvis import ids
from jarvis.events.models import utcnow


class ResearchStatus(StrEnum):
    planning = "planning"
    searching = "searching"
    synthesizing = "synthesizing"
    done = "done"
    partial = "partial"  # ran but incomplete (no sources / synthesis failed) — never a retry storm
    failed = "failed"


class ResearchDepth(StrEnum):
    quick = "quick"
    standard = "standard"
    deep = "deep"


@dataclass(frozen=True)
class DepthCaps:
    max_terms: int
    max_sources: int
    k_per_term: int


# Hard bounds — the harness never exceeds these (no unbounded crawling).
CAPS: dict[ResearchDepth, DepthCaps] = {
    ResearchDepth.quick: DepthCaps(max_terms=3, max_sources=6, k_per_term=4),
    ResearchDepth.standard: DepthCaps(max_terms=5, max_sources=12, k_per_term=5),
    ResearchDepth.deep: DepthCaps(max_terms=8, max_sources=20, k_per_term=6),
}


class Source(BaseModel):
    title: str
    url: str
    snippet: str = ""


class ResearchRun(BaseModel):
    id: str = Field(default_factory=lambda: ids.new_id(ids.RESEARCH))
    query: str
    status: ResearchStatus = ResearchStatus.planning
    depth: ResearchDepth = ResearchDepth.standard
    sub_questions: list[str] = Field(default_factory=list)
    search_terms: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    report_md: str = ""
    document_id: str | None = None
    cost: dict[str, int] = Field(default_factory=dict)  # inferences, sources seen
    schema_version: int = 1
    correlation_id: str = Field(default_factory=lambda: ids.new_id(ids.CORRELATION))
    created_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = None

    @property
    def entity_ref(self) -> str:
        return f"research:{self.id}"
