"""Code-editor agent — propose a compose-file change as an Intent (gated, never auto-applied).

Retrieval finds the target file; the coder model rewrites it in full; the result becomes a
`code.edit_file` Intent routed through the M4 approval+mode gate. The model never writes — only
the capability-scoped executor does, and only under an elevated mode + approval.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError

from jarvis import db, ids
from jarvis.config import get_settings
from jarvis.ingest.code_index import _read_file, search_chunks
from jarvis.intents.models import Intent, IntentReasoning, Risk
from jarvis.intents.repository import insert_intent
from jarvis.models import router

_SYSTEM = (
    "You are Jarvis's coding assistant editing a homelab config file. You are given the FULL "
    "current file and a change request. Respond with ONLY a JSON object "
    '{"new_content": str, "summary": str, "confidence": number 0-1, '
    '"risk": "low"|"medium"|"high", "reversible": bool}. `new_content` MUST be the complete '
    "modified file (not a diff, not a fragment). Make the smallest change that satisfies the "
    "request; preserve everything else exactly. Never invent services or secrets."
)


class CodeEditProposal(BaseModel):
    new_content: str
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    risk: Risk
    reversible: bool


def _parse(content: str) -> CodeEditProposal:
    try:
        return CodeEditProposal.model_validate_json(content)
    except ValidationError as exc:
        raise ValueError(f"edit proposal failed schema validation: {exc}") from exc


def propose_edit(request: str, *, repo: str | None = None) -> Intent:
    """Propose a file edit for `request` as a code.edit_file Intent (status=proposed)."""
    settings = get_settings()
    correlation_id = ids.new_id(ids.CORRELATION)
    repo = repo or settings.code_repo_name  # edit within the configured repo, not all repos

    query_vec = router.embed(request, correlation_id=correlation_id)
    with db.connect() as conn:
        hits = search_chunks(conn, query_vec, k=4, repo=repo)
    if not hits:
        raise ValueError("no indexed code to edit — run `jarvis code index` first")

    # The target file is the top retrieval hit; we read its FULL current content (the chunk
    # is only an excerpt) and pin the edit to that path — the model never chooses the path.
    target_path = hits[0][0]
    current = _read_file(settings.remote_ssh, target_path, settings.code_max_file_bytes)

    messages = [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": (
                f"File: {target_path}\n\n--- current content ---\n{current}\n--- end ---\n\n"
                f"Change request: {request}\n\nReturn the JSON object only."
            ),
        },
    ]
    proposal = _parse(
        str(router.chat("coder", messages, correlation_id=correlation_id, format="json")[
            "message"
        ]["content"])
    )

    with db.connect(autocommit=True) as conn:
        intent = Intent(
            type="code.edit_file",
            target={"path": target_path, "new_content": proposal.new_content},
            reasoning=IntentReasoning(
                summary=proposal.summary, confidence=proposal.confidence,
                risk=proposal.risk, reversible=proposal.reversible,
            ),
            requested_by="code_editor",
            requires_approval=True,
            correlation_id=correlation_id,
        )
        insert_intent(conn, intent)
    return intent
