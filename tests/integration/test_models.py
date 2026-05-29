"""M3 integration: real Ollama via the tunnel — embeddings + chat + memory round-trip.

Skips cleanly if Ollama is unreachable or the configured model tags aren't pulled.
"""

from __future__ import annotations

import psycopg
import pytest

from jarvis.config import get_settings
from jarvis.memory.store import MemoryRecord, PgVectorMemoryStore
from jarvis.models import router

pytestmark = pytest.mark.integration


def test_embed_roundtrips_through_memory_store(db_conn: psycopg.Connection) -> None:
    settings = get_settings()
    try:
        vector = router.embed("postgres restarted after an out-of-memory event")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"embedding model not available — {exc}")

    assert len(vector) == settings.embedding_dim  # 768 for nomic-embed-text

    store = PgVectorMemoryStore()
    record = MemoryRecord(kind="itest_summary", content="oom restart", embedding=vector)
    try:
        store.add(record)
        hits = store.search(vector, k=1, kind="itest_summary")
        assert hits and hits[0][0].id == record.id
    finally:
        db_conn.execute("DELETE FROM memory WHERE id = %s", (record.id,))


def test_chat_returns_text_and_emits_inference_event(monkeypatch) -> None:
    emitted = []
    monkeypatch.setattr(router, "_emit", emitted.append)
    try:
        resp = router.chat(
            "reasoning",
            [{"role": "user", "content": "Reply with the single word: ok"}],
        )
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"reasoning model not available — {exc}")

    assert resp["message"]["content"]
    completed = [e for e in emitted if e.type == "inference.completed"]
    assert completed and completed[0].payload["role"] == "reasoning"
    assert completed[0].payload["duration_ms"] >= 0
