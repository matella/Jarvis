"""AI co-write — a bounded one-shot op that *proposes* a rewrite; it never writes the table.

`propose_edit` runs ONE inference (Hard Rule #2: no agent loop) and returns the proposed markdown.
The caller (a gateway endpoint / the UI diff side-panel) shows it as a diff; on accept it becomes a
normal `document.update` (a version snapshot). Backend is router-resolved (prose-heavy → the
cookbook may pin `claude`); `None` lets the router decide. Replay stays pinned local elsewhere.
"""

from __future__ import annotations

from jarvis.models import scheduler
from jarvis.models.scheduler import Priority

_SYSTEM = (
    "You are a precise writing assistant. Rewrite the TARGET text according to the INSTRUCTION. "
    "Preserve markdown. Return ONLY the rewritten markdown — no preamble, no fences."
)


def propose_edit(
    *,
    body_md: str,
    instruction: str,
    selection: str | None = None,
    backend: str | None = None,
    correlation_id: str | None = None,
) -> str:
    """Return a proposed rewrite of `selection` (or the whole `body_md`) per `instruction`."""
    if not instruction.strip():
        raise ValueError("instruction must be non-empty")
    target = selection if (selection and selection.strip()) else body_md
    user = f"INSTRUCTION:\n{instruction}\n\nTARGET:\n{target}"
    resp = scheduler.chat(
        "reasoning",
        [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
        priority=Priority.INTERACTIVE,
        backend=backend,
        correlation_id=correlation_id,
    )
    return str(resp["message"]["content"]).strip()
