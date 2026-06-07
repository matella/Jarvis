"""News models — canonical_hash dedup + entity refs (pure, no DB)."""

from __future__ import annotations

from jarvis.news.models import NewsArticle, NewsStory, canonical_hash


def test_canonical_hash_ignores_tracking_params() -> None:
    a = canonical_hash(url="https://x.com/story?utm_source=rss&id=1")
    b = canonical_hash(url="https://x.com/story")
    assert a == b


def test_canonical_hash_normalises_host_and_trailing_slash() -> None:
    assert canonical_hash(url="https://X.com/a/") == canonical_hash(url="https://x.com/a")


def test_canonical_hash_falls_back_to_title() -> None:
    h1 = canonical_hash(title="  EU agrees  AI Act timeline ")
    h2 = canonical_hash(title="eu agrees ai act timeline")
    assert h1 == h2 and h1 != canonical_hash(title="something else")


def test_with_hash_fills_and_is_idempotent() -> None:
    art = NewsArticle(source="Reuters", url="https://r.com/a?x=1", title="T").with_hash()
    assert art.canonical_hash == canonical_hash(url="https://r.com/a?x=1")
    assert art.with_hash().canonical_hash == art.canonical_hash  # idempotent


def test_entity_refs() -> None:
    assert NewsArticle(source="x").entity_ref.startswith("news_article:")
    assert NewsStory().entity_ref.startswith("news_story:")
