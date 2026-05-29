"""Coding agent (read-only) — retrieval-augmented Q&A over indexed code/config.

One-shot: embed the question, retrieve the most relevant code chunks, and have the coder model
answer grounded in them — citing files. It never edits anything (deterministic boundary).
"""

from __future__ import annotations

from pydantic import BaseModel

from jarvis import db, ids
from jarvis.ingest.code_index import search_chunks
from jarvis.models import router

_SYSTEM = (
    "You are Jarvis's coding assistant for a homelab. Answer the question using ONLY the "
    "provided code/config excerpts. Cite the relevant files. If the excerpts don't contain "
    "the answer, say so plainly — never invent configuration. Be concise and concrete."
)


class CodeAnswer(BaseModel):
    question: str
    answer: str
    sources: list[str]


def ask(question: str, *, k: int = 6, repo: str | None = None) -> CodeAnswer:
    correlation_id = ids.new_id(ids.CORRELATION)
    query_vec = router.embed(question, correlation_id=correlation_id)
    with db.connect() as conn:
        hits = search_chunks(conn, query_vec, k=k, repo=repo)

    if not hits:
        return CodeAnswer(
            question=question,
            answer="No indexed code found — run `jarvis code index` first.",
            sources=[],
        )

    excerpts = "\n\n".join(
        f"# {path}:{start}-{end}\n{content}" for path, start, end, content, _ in hits
    )
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": f"Excerpts:\n\n{excerpts}\n\nQuestion: {question}"},
    ]
    resp = router.chat("coder", messages, correlation_id=correlation_id)
    return CodeAnswer(
        question=question,
        answer=str(resp["message"]["content"]).strip(),
        sources=[f"{path}:{start}-{end}" for path, start, end, _, _ in hits],
    )
