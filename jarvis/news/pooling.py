"""Pooling — collapse duplicates/syndication and cluster articles into stories. Pure logic.

Two layers: (1) ORIGIN collapse — near-identical bodies (wire copies) share one `origin_id` so
"coverage" counts independent outlets, not republications; (2) STORY clustering — an article joins
an existing same-language story when its embedding is similar enough and it's within the time
window, else it seeds a new story. Pure functions over candidates the repository supplies.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from jarvis.news.embedding import cosine
from jarvis.news.models import NewsArticle, NewsStory

_STORY_SIM = 0.82       # cluster threshold (different stories stay apart)
_ORIGIN_SIM = 0.97      # near-identical → same origin (syndication/wire copy)
_WINDOW_H = 48


@dataclass(frozen=True)
class PoolMatch:
    story_id: str | None   # existing story to attach to, or None → create new
    origin_id: str         # the origin this article belongs to


def same_origin(a: NewsArticle, b: NewsArticle, *, threshold: float = _ORIGIN_SIM) -> bool:
    """A wire/syndicated copy of the same text → one origin (don't double-count coverage)."""
    if a.embedding and b.embedding:
        return cosine(a.embedding, b.embedding) >= threshold
    return a.canonical_hash == b.canonical_hash


def pick_story(
    article: NewsArticle,
    candidates: list[NewsStory],
    *,
    now: datetime,
    sim_threshold: float = _STORY_SIM,
    window_h: int = _WINDOW_H,
) -> str | None:
    """The best same-language story to attach `article` to, or None to start a new one.

    `candidates` are recent stories the repository fetched (already same-language is fine but we
    re-check). Returns the highest-similarity story above threshold within the time window.
    """
    if not article.embedding:
        return None
    cutoff = now - timedelta(hours=window_h)
    best_id, best_sim = None, sim_threshold
    for story in candidates:
        if story.lang != article.lang or not story.embedding:
            continue
        if story.created_at < cutoff:
            continue
        sim = cosine(article.embedding, story.embedding)
        if sim >= best_sim:
            best_id, best_sim = story.id, sim
    return best_id


def count_independent_origins(articles: list[NewsArticle]) -> int:
    """Distinct origin_ids across a story's articles (falls back to article id when unset)."""
    return len({a.origin_id or a.id for a in articles})
