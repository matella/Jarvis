"""The generic presenter: `auto_artifact` (deterministic) + `present` (one-shot format chooser)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

# Artifact.data is dict[str, Any]; the universal renderer reads `data["value"]`, so ANY shape
# (list, scalar, nested object) round-trips through a uniform envelope.
_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "kind": {"type": "string", "enum": ["auto", "markdown"]},
        "summary": {"type": "string"},
    },
    "required": ["kind"],
}


def auto_artifact(title: str, data: Any):  # noqa: ANN401 — presents arbitrary data by design
    """Wrap any data as a universal `auto` artifact (the frontend infers the best layout)."""
    from jarvis.agents.conversation import Artifact

    return Artifact(kind="auto", title=title or "Result", data={"value": data})


def present(
    data: Any,  # noqa: ANN401
    *,
    request: str = "",
    title: str | None = None,
    backend: str | None = None,
    chat_fn: Callable[..., dict] | None = None,
):
    """One-shot: pick how to show `data` for `request`. Structured → `auto`; prose → `markdown`.
    Falls back to `auto_artifact` on any error, so a presentation never fails the turn."""
    from jarvis.agents.conversation import Artifact

    try:
        from jarvis.models.scheduler import Priority
        from jarvis.models.scheduler import chat as sched_chat

        chat_fn = chat_fn or sched_chat
        blob = json.dumps(data, default=str)[:3000]
        prompt = (
            "Decide how to present DATA for the user's REQUEST. Return JSON {title,kind,summary}. "
            "kind='auto' when DATA is structured (records/lists/numbers — the UI renders it as a "
            "table); kind='markdown' for a short prose explanation. title: a concise heading. "
            "summary: for markdown, the explanation; for auto, an optional one-line caption.\n\n"
            f"REQUEST: {request}\n\nDATA: {blob}"
        )
        resp = chat_fn("reasoning", [{"role": "user", "content": prompt}],
                       priority=Priority.INTERACTIVE, backend=backend, format=_SCHEMA)
        choice = json.loads(str(resp["message"]["content"]))
        heading = str(choice.get("title") or title or "Result")
        if choice.get("kind") == "markdown" and choice.get("summary"):
            return Artifact(kind="markdown", title=heading, data={"text": str(choice["summary"])})
        return auto_artifact(heading, data)
    except Exception:  # noqa: BLE001 — any failure → the deterministic universal artifact
        return auto_artifact(title or "Result", data)
