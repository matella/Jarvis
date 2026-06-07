"""News pooling + embedding cosine — synthetic vectors, no DB/model."""

from __future__ import annotations

from datetime import timedelta

from jarvis.events.models import utcnow
from jarvis.news.embedding import cosine
from jarvis.news.models import NewsArticle, NewsStory
from jarvis.news.pooling import count_independent_origins, pick_story, same_origin


def _art(vec, lang="en", **kw):
    return NewsArticle(source=kw.pop("source", "X"), lang=lang, embedding=vec, **kw)


def test_cosine_basic() -> None:
    assert cosine([1, 0], [1, 0]) == 1.0
    assert cosine([1, 0], [0, 1]) == 0.0
    assert cosine([], [1, 0]) == 0.0


def test_same_origin_collapses_near_identical() -> None:
    a = _art([1.0, 0.0, 0.0])
    b = _art([0.999, 0.01, 0.0])           # ~identical → wire copy
    c = _art([0.0, 1.0, 0.0])              # different
    assert same_origin(a, b) is True
    assert same_origin(a, c) is False


def test_pick_story_attaches_to_similar_same_lang_in_window() -> None:
    now = utcnow()
    story = NewsStory(lang="en", embedding=[1.0, 0.0, 0.0], created_at=now - timedelta(hours=2))
    other = NewsStory(lang="en", embedding=[0.0, 1.0, 0.0], created_at=now)
    art = _art([0.95, 0.05, 0.0])
    assert pick_story(art, [other, story], now=now) == story.id


def test_pick_story_new_when_dissimilar_or_other_lang_or_stale() -> None:
    now = utcnow()
    similar_fr = NewsStory(lang="fr", embedding=[1.0, 0.0, 0.0], created_at=now)  # wrong lang
    stale = NewsStory(lang="en", embedding=[1.0, 0.0, 0.0], created_at=now - timedelta(hours=72))
    art = _art([1.0, 0.0, 0.0], lang="en")
    assert pick_story(art, [similar_fr, stale], now=now) is None


def test_count_independent_origins_collapses_syndication() -> None:
    arts = [_art([1, 0], origin_id="o1"), _art([1, 0], origin_id="o1"),
            _art([0, 1], origin_id="o2")]
    assert count_independent_origins(arts) == 2
