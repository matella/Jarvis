"""Multilingual embeddings for news (bge-m3, CPU) — separate from Jarvis's nomic search index.

Kept distinct so good FR/NL clustering/search doesn't require migrating the global embedding dim.
bge-m3 runs on CPU, so it does NOT take the GPU inference semaphore — news embedding at volume never
blocks interactive chat/voice on the card.
"""

from __future__ import annotations

import math

_NEWS_EMBED_MODEL = "bge-m3"


def embed_news(text: str) -> list[float]:
    """Embed `text` with the multilingual news embedder. Empty → empty vector (no model call)."""
    text = (text or "").strip()
    if not text:
        return []
    from jarvis.models.client import embeddings

    return embeddings(_NEWS_EMBED_MODEL, text)


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity in [-1, 1]; 0.0 when either vector is empty/zero."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
