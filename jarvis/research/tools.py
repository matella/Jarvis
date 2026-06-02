"""Deep-research capability tool — GATED (web egress + inference budget = an external effect).

`side_effects=True` makes the conversation agent build a gated intent; the human confirms (or
`semi_autonomous` runs it as low-risk/reversible work). On run: the bounded harness → persist the
run → save the report as a linked Document (cross-module) → awareness event. Replay pins local; the
synthesis backend is router-resolved (cookbook may pin claude).
"""

from __future__ import annotations

from typing import Any

from jarvis import db
from jarvis.documents import repository as docs_repo
from jarvis.documents.models import Document
from jarvis.modules.awareness import emit_awareness
from jarvis.research import repository
from jarvis.research.harness import run_harness
from jarvis.research.models import ResearchDepth, ResearchStatus
from jarvis.tools.contract import Rollback, Tool
from jarvis.tools.registry import register


def _run(target: dict[str, Any], *, timeout_s: int) -> dict[str, Any]:
    query = target.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("research query is required")
    depth_raw = target.get("depth", "standard")
    try:
        depth = ResearchDepth(depth_raw)
    except ValueError as exc:
        raise ValueError(f"invalid depth: {depth_raw!r}") from exc

    run = run_harness(query.strip(), depth=depth)

    # Cross-module: a successful report lands as a Document linked back to the run.
    if run.status is ResearchStatus.done and run.report_md:
        doc = Document(
            title=f"Research: {query.strip()[:120]}",
            body_md=run.report_md,
            source_entity_ref=run.entity_ref,
        )
        with db.connect() as conn:
            docs_repo.create(conn, doc, author="research")
        run = run.model_copy(update={"document_id": doc.id})

    with db.connect() as conn:
        repository.save(conn, run)
    emit_awareness(
        "research.completed", source="research", entity_ref=run.entity_ref,
        correlation_id=run.correlation_id, status=run.status.value,
        sources=len(run.sources), document_id=run.document_id,
    )
    return {"run_id": run.id, "status": run.status.value, "document_id": run.document_id}


register(Tool(
    name="research.run", version=1, permissions=["research:run", "web:read"],
    side_effects=True,  # external (web egress + budget) → the agent gates it
    idempotent=False, max_retries=0, timeout_seconds=600, rollback=Rollback.none, run=_run,
))
