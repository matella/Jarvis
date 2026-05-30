"""Knowledge-base ingest (backlog #7) — index runbooks/notes/wiki prose into memory.

Extends the P3 code-intelligence indexer (which reads + redacts files over SSH) from config/code to
prose docs. Markdown/text chunks are sanitized (secrets/PII) and embedded into the `memory` table as
kind="kb", so the conversation agent's existing vector retrieval surfaces them automatically — the
agent can ground answers in your own docs without any new retrieval path.
"""

from __future__ import annotations

from jarvis.config import get_settings
from jarvis.ingest.code_index import _chunk, _list_files, _read_file
from jarvis.memory.store import MemoryRecord, PgVectorMemoryStore
from jarvis.security.sanitize import sanitize

_DOC_EXTENSIONS = (".md", ".markdown", ".txt", ".rst")


def _is_doc(path: str) -> bool:
    return path.lower().endswith(_DOC_EXTENSIONS)


def kb_chunks(text: str, path: str, chunk_lines: int) -> list[tuple[str, dict]]:
    """Sanitize + chunk a doc into (content, metadata) pairs. Pure — no I/O."""
    clean = sanitize(text)
    title = path.rsplit("/", 1)[-1]
    out: list[tuple[str, dict]] = []
    for start, end, content in _chunk(clean, chunk_lines):
        if content.strip():
            out.append((content, {"path": path, "title": title, "lines": [start, end]}))
    return out


def index_kb(*, paths: list[str] | None = None, store: PgVectorMemoryStore | None = None) -> int:
    """Index configured KB paths into memory (kind='kb'). Returns chunk count stored."""
    from jarvis.models.router import embed

    s = get_settings()
    paths = paths or s.kb_paths
    if not paths or not s.remote_ssh:
        return 0
    store = store or PgVectorMemoryStore()
    stored = 0
    for root in paths:
        for path in _list_files(s.remote_ssh, root):
            if not _is_doc(path):
                continue
            text = _read_file(s.remote_ssh, path, s.kb_max_file_bytes)
            for content, meta in kb_chunks(text, path, s.kb_chunk_lines):
                store.add(MemoryRecord(kind="kb", content=content, embedding=embed(content),
                                       metadata=meta))
                stored += 1
    return stored


def search_kb(query: str, *, k: int = 5, store: PgVectorMemoryStore | None = None) -> list[str]:
    """Retrieve KB chunks relevant to a query (for `jarvis kb search` / grounding)."""
    from jarvis.models.router import embed

    store = store or PgVectorMemoryStore()
    vec = embed(query)
    return [rec.content for rec, _dist in store.search(vec, k=k, kind="kb")]
