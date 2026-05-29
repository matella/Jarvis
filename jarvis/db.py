"""psycopg3 connection factory.

Hands out connections with the pgvector type registered and `dict_row` rows (so
repositories can build Pydantic models straight from a row mapping). A pool is
deferred to M2, when the consumer/projector need concurrent access.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from jarvis.config import get_settings


@contextmanager
def connect(*, autocommit: bool = False) -> Iterator[psycopg.Connection]:
    """Yield a connection; commits on clean exit (psycopg context semantics)."""
    with psycopg.connect(
        get_settings().postgres_dsn,
        autocommit=autocommit,
        row_factory=dict_row,
    ) as conn:
        register_vector(conn)
        yield conn
