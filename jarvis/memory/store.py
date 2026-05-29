"""Vector memory behind a `MemoryStore` interface.

The ABC is the seam DECISIONS.md promised for a future Qdrant swap; the only
implementation today is pgvector (cosine). Embedding width is validated against the
configured dimension so a mismatched embedder fails loudly rather than corrupting the
index.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Any

import numpy as np
import psycopg
from psycopg.types.json import Json
from pydantic import BaseModel, Field

from jarvis import ids
from jarvis.config import get_settings
from jarvis.db import connect
from jarvis.events.models import utcnow

ConnFactory = Callable[[], AbstractContextManager[psycopg.Connection]]


class MemoryRecord(BaseModel):
    id: str = Field(default_factory=lambda: ids.new_id(ids.MEMORY))
    kind: str
    content: str
    embedding: list[float]
    metadata: dict[str, Any] = Field(default_factory=dict)
    ts: datetime = Field(default_factory=utcnow)


class MemoryStore(ABC):
    @abstractmethod
    def add(self, record: MemoryRecord) -> None:
        """Persist a record (with its embedding)."""

    @abstractmethod
    def search(
        self, embedding: list[float], k: int = 5, *, kind: str | None = None
    ) -> list[tuple[MemoryRecord, float]]:
        """Return the k nearest records as (record, cosine_distance), nearest first."""


class PgVectorMemoryStore(MemoryStore):
    def __init__(self, conn_factory: ConnFactory = connect, dim: int | None = None) -> None:
        self._conn_factory = conn_factory
        self._dim = dim if dim is not None else get_settings().embedding_dim

    def _check_dim(self, embedding: list[float]) -> None:
        if len(embedding) != self._dim:
            raise ValueError(
                f"embedding has {len(embedding)} dims, expected {self._dim}"
            )

    def add(self, record: MemoryRecord) -> None:
        self._check_dim(record.embedding)
        with self._conn_factory() as conn:
            conn.execute(
                "INSERT INTO memory (id, kind, content, embedding, metadata, ts) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    record.id,
                    record.kind,
                    record.content,
                    np.asarray(record.embedding, dtype=np.float32),
                    Json(record.metadata),
                    record.ts,
                ),
            )

    def search(
        self, embedding: list[float], k: int = 5, *, kind: str | None = None
    ) -> list[tuple[MemoryRecord, float]]:
        self._check_dim(embedding)
        query = np.asarray(embedding, dtype=np.float32)
        sql = (
            "SELECT id, kind, content, embedding, metadata, ts, "
            "embedding <=> %s AS distance FROM memory"
        )
        params: list[Any] = [query]
        if kind is not None:
            sql += " WHERE kind = %s"
            params.append(kind)
        sql += " ORDER BY distance ASC LIMIT %s"
        params.append(k)

        with self._conn_factory() as conn:
            rows = conn.execute(sql, params).fetchall()

        results: list[tuple[MemoryRecord, float]] = []
        for row in rows:
            distance = float(row.pop("distance"))
            row["embedding"] = [float(x) for x in row["embedding"]]
            results.append((MemoryRecord(**row), distance))
        return results
