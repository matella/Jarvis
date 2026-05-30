"""SearchProvider interface + result type. Swappable (SearXNG now, a cloud provider later)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    engine: str = ""


class SearchProvider(Protocol):
    name: str

    def search(self, query: str, *, k: int = 5) -> list[SearchResult]:
        """Return up to k normalized, sanitized results. Raises on transport/egress failure."""
        ...
