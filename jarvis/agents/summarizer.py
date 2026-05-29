"""One-shot summarizer agent.

A specialized reasoning endpoint, not a personality: one inference → one structured output.
It summarizes deterministically-assembled recent events into prose, attaches a deterministic
list of notable (warning+) events, and stores the summary as episodic memory so future
context assembly can retrieve it.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import BaseModel

from jarvis import db, ids
from jarvis.core.assembly import assemble_context
from jarvis.events.models import Severity, utcnow
from jarvis.memory.store import MemoryRecord, MemoryStore, PgVectorMemoryStore
from jarvis.models import router

_NOTABLE = {Severity.warning, Severity.error, Severity.critical}

_SYSTEM = (
    "You are Jarvis, an operational intelligence assistant for a homelab. "
    "Summarize the provided infrastructure events concisely and factually for an operator. "
    "Group related events, call out anything that needs attention, and be brief. "
    "Only describe events that appear in the input — never invent containers, times, or causes."
)


class NotableEvent(BaseModel):
    id: str
    occurred_at: datetime
    type: str
    severity: str
    entity_ref: str | None = None


class SummaryResult(BaseModel):
    window: str
    event_count: int
    summary: str
    notable: list[NotableEvent]


def summarize(since: timedelta, *, store: MemoryStore | None = None) -> SummaryResult:
    correlation_id = ids.new_id(ids.CORRELATION)
    since_dt = utcnow() - since

    with db.connect() as conn:
        ctx = assemble_context(
            conn, since=since_dt, query="recent infrastructure incidents and lifecycle changes",
            store=store,
        )

    if not ctx.events:
        return SummaryResult(
            window=_format_window(since),
            event_count=0,
            summary="No events recorded in this window.",
            notable=[],
        )

    messages = [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": (
                f"Events since {since_dt:%Y-%m-%d %H:%M} UTC:\n\n{ctx.prompt}\n\n"
                "Write a short operational summary (2-4 sentences)."
            ),
        },
    ]
    resp = router.chat(
        "reasoning", messages, correlation_id=correlation_id, context_ref=ctx.context_ref
    )
    summary_text = str(resp["message"]["content"]).strip()

    notable = [
        NotableEvent(
            id=e.id, occurred_at=e.occurred_at, type=e.type,
            severity=e.severity.value, entity_ref=e.entity_ref,
        )
        for e in ctx.events
        if e.severity in _NOTABLE
    ]
    result = SummaryResult(
        window=_format_window(since),
        event_count=len(ctx.events),
        summary=summary_text,
        notable=notable,
    )

    # Episodic memory — store the summary so future runs can retrieve it by similarity.
    try:
        vector = router.embed(summary_text, correlation_id=correlation_id)
        store = store or PgVectorMemoryStore()
        store.add(
            MemoryRecord(
                kind="summary",
                content=summary_text,
                embedding=vector,
                metadata={"window": result.window, "event_count": result.event_count},
            )
        )
    except Exception:
        pass  # memory write is best-effort; the summary still returns

    return result


def _format_window(since: timedelta) -> str:
    seconds = int(since.total_seconds())
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds % size == 0 and seconds >= size:
            return f"{seconds // size}{unit}"
    return f"{seconds}s"
