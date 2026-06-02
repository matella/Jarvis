"""Shared module search hook — index builds the record; search maps + filters. No DB/Ollama."""

from __future__ import annotations

from jarvis.memory.store import MemoryRecord, MemoryStore
from jarvis.modules import search as ms


class _FakeStore(MemoryStore):
    def __init__(self, results: list[tuple[MemoryRecord, float]] | None = None) -> None:
        self.added: list[MemoryRecord] = []
        self._results = results or []

    def add(self, record: MemoryRecord) -> None:
        self.added.append(record)

    def search(self, embedding, k=5, *, kind=None):  # type: ignore[override]
        return self._results[:k]


def _embed(_text: str) -> list[float]:
    return [0.0, 1.0, 0.0]


def test_index_entity_builds_module_record_with_facets() -> None:
    store = _FakeStore()
    ms.index_entity(
        source="notes", entity_ref="note:1", title="Groceries", text="milk and eggs",
        store=store, embed=_embed,
    )
    assert len(store.added) == 1
    rec = store.added[0]
    assert rec.kind == ms.KIND
    assert rec.metadata == {"source": "notes", "entity_ref": "note:1", "title": "Groceries"}
    assert "Groceries" in rec.content and "milk and eggs" in rec.content
    assert rec.embedding == [0.0, 1.0, 0.0]


def test_search_maps_hits_and_filters_by_source() -> None:
    recs = [
        (MemoryRecord(kind=ms.KIND, content="a", embedding=[0.0],
                      metadata={"source": "notes", "entity_ref": "note:1", "title": "A"}), 0.1),
        (MemoryRecord(kind=ms.KIND, content="b", embedding=[0.0],
                      metadata={"source": "tasks", "entity_ref": "task:9", "title": "B"}), 0.2),
    ]
    store = _FakeStore(recs)
    all_hits = ms.search("q", store=store, embed=_embed)
    assert {h.source for h in all_hits} == {"notes", "tasks"}
    assert all_hits[0].entity_ref == "note:1" and all_hits[0].title == "A"

    only_tasks = ms.search("q", sources=["tasks"], store=store, embed=_embed)
    assert [h.entity_ref for h in only_tasks] == ["task:9"]


def test_search_respects_k() -> None:
    recs = [
        (MemoryRecord(kind=ms.KIND, content=str(i), embedding=[0.0],
                      metadata={"source": "notes", "entity_ref": f"note:{i}", "title": str(i)}),
         i / 10)
        for i in range(10)
    ]
    assert len(ms.search("q", k=3, store=_FakeStore(recs), embed=_embed)) == 3
