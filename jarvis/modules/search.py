"""Shared search hook for user-document modules — index/search/purge over the `memory` table.

No new vector store (foundation rule): module content is embedded into the existing `memory` table
with `kind="module"` and a `source` facet (notes/tasks/recipes/documents/calendar) in metadata, so
the conversation agent's retrieval + the Cmd-K palette find it for free. `entity_ref` in metadata
links a vector row back to its owning module row, and lets us purge/reindex on edit + delete.

Core indexing/search logic takes an injected `store` + `embed` so it unit-tests without Ollama or a
DB; `purge_entity`/`reindex_entity` do raw SQL (the `MemoryStore` ABC has no delete) and are
integration-tested.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass

import psycopg

from jarvis.db import connect
from jarvis.memory.store import MemoryRecord, MemoryStore, PgVectorMemoryStore
from jarvis.security.sanitize import sanitize

KIND = "module"  # one memory kind for all user-document modules; `source` facet distinguishes them

ConnFactory = Callable[[], AbstractContextManager[psycopg.Connection]]
Embedder = Callable[[str], list[float]]


@dataclass(frozen=True)
class Hit:
    entity_ref: str
    source: str
    title: str
    content: str
    distance: float


def _default_embed(text: str) -> list[float]:
    from jarvis.models.router import embed  # lazy — don't import the model stack at module load

    return embed(text)


def _indexable(title: str, text: str) -> str:
    # Title boosts recall; sanitize so secrets/PII never land in the vector index (defense-in-depth).
    return sanitize(f"{title}\n{text}".strip())


def index_entity(
    *,
    source: str,
    entity_ref: str,
    title: str,
    text: str,
    store: MemoryStore | None = None,
    embed: Embedder | None = None,
) -> None:
    """Embed a module entity's text into `memory` (kind='module', source/entity_ref/title facets)."""
    store = store or PgVectorMemoryStore()
    embed = embed or _default_embed
    content = _indexable(title, text)
    store.add(
        MemoryRecord(
            kind=KIND,
            content=content,
            embedding=embed(content),
            metadata={"source": source, "entity_ref": entity_ref, "title": title},
        )
    )


def purge_entity(entity_ref: str, *, conn_factory: ConnFactory = connect) -> int:
    """Remove all vector rows for an entity (on delete/archive). Returns rows removed."""
    with conn_factory() as conn:
        cur = conn.execute(
            "DELETE FROM memory WHERE kind = %s AND metadata->>'entity_ref' = %s",
            (KIND, entity_ref),
        )
        return cur.rowcount


def reindex_entity(
    *,
    source: str,
    entity_ref: str,
    title: str,
    text: str,
    store: MemoryStore | None = None,
    embed: Embedder | None = None,
    conn_factory: ConnFactory = connect,
) -> None:
    """Purge prior vectors for the entity then index the current content (on update)."""
    purge_entity(entity_ref, conn_factory=conn_factory)
    index_entity(
        source=source, entity_ref=entity_ref, title=title, text=text, store=store, embed=embed
    )


def search(
    query: str,
    *,
    sources: list[str] | None = None,
    k: int = 8,
    store: MemoryStore | None = None,
    embed: Embedder | None = None,
) -> list[Hit]:
    """Semantic search across module content; optionally restrict to certain `sources`."""
    store = store or PgVectorMemoryStore()
    embed = embed or _default_embed
    # Over-fetch then post-filter by source (the store filters by `kind`, not metadata).
    raw = store.search(embed(query), k=k * 3 if sources else k, kind=KIND)
    hits: list[Hit] = []
    for rec, dist in raw:
        meta = rec.metadata or {}
        src = str(meta.get("source", ""))
        if sources and src not in sources:
            continue
        hits.append(
            Hit(
                entity_ref=str(meta.get("entity_ref", "")),
                source=src,
                title=str(meta.get("title", "")),
                content=rec.content,
                distance=dist,
            )
        )
    return hits[:k]
