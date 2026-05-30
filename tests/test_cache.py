"""Backlog #8 unit: embedding cache (LRU, hit/miss, eviction)."""

from __future__ import annotations

from jarvis.models.cache import EmbeddingCache


def test_hit_and_miss() -> None:
    c = EmbeddingCache(capacity=10)
    assert c.get("m", "hello") is None  # miss
    c.put("m", "hello", [0.1, 0.2])
    assert c.get("m", "hello") == [0.1, 0.2]  # hit
    assert c.stats()["hits"] == 1 and c.stats()["misses"] == 1


def test_keyed_by_model_and_text() -> None:
    c = EmbeddingCache(capacity=10)
    c.put("m1", "x", [1.0])
    assert c.get("m2", "x") is None  # different model → miss
    assert c.get("m1", "y") is None  # different text → miss
    assert c.get("m1", "x") == [1.0]


def test_lru_eviction() -> None:
    c = EmbeddingCache(capacity=2)
    c.put("m", "a", [1.0])
    c.put("m", "b", [2.0])
    c.get("m", "a")  # touch a → b is now oldest
    c.put("m", "c", [3.0])  # evicts b
    assert c.get("m", "b") is None
    assert c.get("m", "a") == [1.0]
    assert c.get("m", "c") == [3.0]


def test_zero_capacity_noop() -> None:
    c = EmbeddingCache(capacity=0)
    c.put("m", "a", [1.0])
    assert c.get("m", "a") is None
