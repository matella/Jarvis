"""Multilingual embeddings for news — separate from Jarvis's nomic search index.

snowflake-arctic-embed2 (1024-dim, multilingual, CPU): stable in Ollama where bge-m3 emitted NaN on
ordinary news text. Uses the modern `/api/embed` endpoint and is fully fault-tolerant — any failure
returns an empty vector so one bad article never crashes the worker. CPU → no GPU-semaphore
contention with interactive chat/voice.
"""

from __future__ import annotations

import math

import httpx

from jarvis.config import get_settings

_NEWS_EMBED_MODEL = "snowflake-arctic-embed2"


def embed_news(text: str) -> list[float]:
    """Embed `text` with the news embedder. Empty/failure → empty vector (never raises)."""
    text = (text or "").strip()
    if not text:
        return []
    try:
        resp = httpx.post(
            f"{get_settings().ollama_url}/api/embed",
            json={"model": _NEWS_EMBED_MODEL, "input": text[:8000]}, timeout=30.0,
        )
        resp.raise_for_status()
        vecs = resp.json().get("embeddings", [])
        return [float(x) for x in vecs[0]] if vecs else []
    except Exception:  # noqa: BLE001 — embedding is best-effort; a failure must not crash the worker
        return []


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
