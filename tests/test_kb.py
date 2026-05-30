"""Backlog #7 unit: KB chunking — sanitized, metadata-tagged, doc-filtered (pure)."""

from __future__ import annotations

from jarvis.ingest.kb import _is_doc, kb_chunks


def test_is_doc_filters_extensions() -> None:
    assert _is_doc("/notes/runbook.md") is True
    assert _is_doc("/notes/INCIDENTS.txt") is True
    assert _is_doc("/notes/diagram.png") is False
    assert _is_doc("/etc/config.yaml") is False


def test_kb_chunks_sanitize_and_tag() -> None:
    text = "\n".join([f"line {i}" for i in range(50)]) + "\nemail ops@example.com if stuck\n"
    chunks = kb_chunks(text, "/runbooks/db.md", chunk_lines=40)
    assert len(chunks) >= 2  # 50+ lines at 40/chunk → multiple chunks
    content, meta = chunks[0]
    assert meta["path"] == "/runbooks/db.md" and meta["title"] == "db.md"
    assert "lines" in meta
    # PII in any chunk is redacted
    joined = "\n".join(c for c, _ in chunks)
    assert "ops@example.com" not in joined
    assert "<redacted>" in joined


def test_kb_chunks_skips_empty() -> None:
    assert kb_chunks("   \n  \n", "/x.md", chunk_lines=40) == []
