"""News boundary models — a scraped article and a pooled story (cluster). Tables own the truth.

`canonical_hash` normalizes a URL (drop query/fragment, lowercase host) so the same link with
tracking params dedups to one row; it falls back to a normalized-title hash when no URL is given.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, Field

from jarvis import ids
from jarvis.events.models import utcnow

_EMBED_DIM = 1024  # bge-m3
_WS_RE = re.compile(r"\s+")


def canonical_hash(*, url: str = "", title: str = "") -> str:
    """Stable dedup key: normalized URL if present, else normalized title. Always non-empty."""
    if url.strip():
        p = urlsplit(url.strip())
        norm = urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), "", ""))
        basis = norm or url.strip()
    else:
        basis = _WS_RE.sub(" ", title.lower()).strip()
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


class NewsArticle(BaseModel):
    id: str = Field(default_factory=lambda: ids.new_id(ids.NEWSARTICLE))
    source: str
    origin_id: str | None = None          # syndication group — wire copies share one origin
    url: str = ""
    canonical_hash: str = ""
    lang: str = "en"
    title: str = ""
    body: str = ""
    published_at: datetime | None = None
    summary: str = ""                      # tier A
    topic: str = ""                        # tier A tag
    region: str = ""                       # tier A tag
    embedding: list[float] | None = None
    story_id: str | None = None
    schema_version: int = 1
    recorded_at: datetime = Field(default_factory=utcnow)

    def with_hash(self) -> NewsArticle:
        """Return a copy with canonical_hash filled from url/title (idempotent)."""
        h = self.canonical_hash or canonical_hash(url=self.url, title=self.title)
        return self.model_copy(update={"canonical_hash": h})

    @property
    def entity_ref(self) -> str:
        return f"news_article:{self.id}"


class NewsStory(BaseModel):
    id: str = Field(default_factory=lambda: ids.new_id(ids.NEWSSTORY))
    lang: str = "en"
    title: str = ""
    synthesized_body: str = ""             # tier B (empty until synthesized)
    title_fr: str = ""                     # cached French translation (default display language)
    body_fr: str = ""                      # "" = not yet translated, or the story is already FR
    translated_hash: str = ""              # hash of the source title+body that was translated
    disagreements_fr: list[dict] = Field(default_factory=list)   # FR "where sources disagree"
    claims_json: list[dict] = Field(default_factory=list)        # claim → source citations
    disagreements_json: list[dict] = Field(default_factory=list)
    source_count: int = 0                  # distinct articles
    origin_count: int = 0                  # distinct independent origins (syndication-collapsed)
    top_at: datetime | None = None         # when it was last selected as a top story
    embedding: list[float] | None = None
    schema_version: int = 1
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @property
    def entity_ref(self) -> str:
        return f"news_story:{self.id}"
