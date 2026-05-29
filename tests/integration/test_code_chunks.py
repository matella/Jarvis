"""P3 code-chunks integration: store round-trip + real embedding dimension."""

from __future__ import annotations

import psycopg
import pytest

from jarvis.config import get_settings
from jarvis.ingest.code_index import delete_repo, insert_chunks, search_chunks

pytestmark = pytest.mark.integration


def test_chunk_store_roundtrip(db_conn: psycopg.Connection) -> None:
    repo = "itest-coderepo"
    near = [1.0] + [0.0] * 767
    far = [0.0, 1.0] + [0.0] * 766
    rows = [
        (("compose/a.yml", 1, 5, "network_mode: service:gluetun"), near),
        (("compose/b.yml", 1, 5, "image: postgres:16"), far),
    ]
    try:
        insert_chunks(db_conn, repo, rows)
        hits = search_chunks(db_conn, near, k=1, repo=repo)
        assert hits and hits[0][0] == "compose/a.yml"
        assert hits[0][3] == "network_mode: service:gluetun"
    finally:
        delete_repo(db_conn, repo)


def test_embed_many_returns_correct_dim() -> None:
    from jarvis.models import router

    try:
        vectors = router.embed_many(["network_mode: service:gluetun", "image: postgres"])
    except Exception as exc:  # noqa: BLE001
        if "connect" in str(exc).lower():
            pytest.skip(f"Ollama unavailable — {exc}")
        raise
    assert len(vectors) == 2
    assert all(len(v) == get_settings().embedding_dim for v in vectors)
