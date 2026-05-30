"""Cost-aware inference caching (backlog #8).

Embeddings are deterministic for a given (model, text), so caching them avoids recompute entirely —
the cheap, correctness-safe win. (We deliberately do NOT cache chat/reasoning responses: inference
is non-deterministic and replaying a stale decision would violate "log the I/O, not the model";
and on a single 8 GB GPU, model *tiering* would add swaps that cost more than they save — so
cost-awareness here is caching + the scheduler's swap limiter, not a fast/slow model split.)
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict

from jarvis.config import get_settings


class EmbeddingCache:
    """Bounded LRU of (model, text-hash) → vector. Thread-safe."""

    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self._store: OrderedDict[str, list[float]] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    @staticmethod
    def _key(model: str, text: str) -> str:
        return model + ":" + hashlib.sha256(text.encode()).hexdigest()

    def get(self, model: str, text: str) -> list[float] | None:
        key = self._key(model, text)
        with self._lock:
            vec = self._store.get(key)
            if vec is None:
                self.misses += 1
                return None
            self._store.move_to_end(key)  # LRU touch
            self.hits += 1
            return vec

    def put(self, model: str, text: str, vector: list[float]) -> None:
        if self.capacity <= 0:
            return
        key = self._key(model, text)
        with self._lock:
            self._store[key] = vector
            self._store.move_to_end(key)
            while len(self._store) > self.capacity:
                self._store.popitem(last=False)  # evict the oldest

    def stats(self) -> dict:
        with self._lock:
            total = self.hits + self.misses
            return {
                "size": len(self._store), "capacity": self.capacity,
                "hits": self.hits, "misses": self.misses,
                "hit_rate": round(self.hits / total, 3) if total else 0.0,
            }


_CACHE = EmbeddingCache(get_settings().embedding_cache_size)


def get_cache() -> EmbeddingCache:
    return _CACHE


def enabled() -> bool:
    return get_settings().embedding_cache_enabled
