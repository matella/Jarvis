"""Deterministic context assembly — the intelligence is here, not in the model.

Builds a token-budgeted context from recency + entity match + vector relevance. The LLM is
later handed the rendered prompt and only *compresses* it; it never decides what to retrieve.
`context_ref` is a stable hash of the rendered prompt + reasoning model, the seed of the
"why did it decide this?" answer.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

import psycopg

from jarvis.config import get_settings
from jarvis.events.models import Event
from jarvis.memory.store import MemoryRecord, MemoryStore, PgVectorMemoryStore

_CHARS_PER_TOKEN = 4  # rough budget heuristic; a real tokenizer can replace this later
_EVENT_FETCH_LIMIT = 500


@dataclass
class AssembledContext:
    events: list[Event]
    memories: list[MemoryRecord]
    prompt: str
    context_ref: str


def _fetch_events(conn: psycopg.Connection, since: datetime, entity: str | None) -> list[Event]:
    sql = "SELECT * FROM events WHERE occurred_at >= %s"
    params: list[object] = [since]
    if entity is not None:
        sql += " AND entity_ref = %s"
        params.append(entity)
    sql += " ORDER BY id DESC LIMIT %s"
    params.append(_EVENT_FETCH_LIMIT)
    return [Event(**row) for row in conn.execute(sql, params).fetchall()]


def _render_event(event: Event) -> str:
    payload = json.dumps(event.payload, default=str, separators=(",", ":"))
    if len(payload) > 200:
        payload = payload[:200] + "…"
    return (
        f"[{event.occurred_at:%Y-%m-%d %H:%M:%S}] {event.severity.value:8} "
        f"{event.type} {event.entity_ref or '-'} {payload}"
    )


def assemble_context(
    conn: psycopg.Connection,
    *,
    since: datetime,
    entity: str | None = None,
    query: str | None = None,
    budget_tokens: int | None = None,
    store: MemoryStore | None = None,
) -> AssembledContext:
    settings = get_settings()
    char_budget = (budget_tokens or settings.inference_context) * _CHARS_PER_TOKEN
    events = _fetch_events(conn, since, entity)

    # Vector relevance: embed the query and pull related prior memories. Assembly decides to
    # retrieve (deterministic) — the model does not. Degrades gracefully if no embedder.
    memories: list[MemoryRecord] = []
    if query:
        try:
            from jarvis.models.router import embed

            query_vec = embed(query)
            store = store or PgVectorMemoryStore()
            memories = [record for record, _distance in store.search(query_vec, k=5)]
        except Exception:
            memories = []

    memory_text = "\n".join(f"- ({m.kind}) {m.content}" for m in memories)
    used = len(memory_text)
    kept: list[Event] = []
    for event in events:  # newest first
        line = _render_event(event)
        if used + len(line) + 1 > char_budget:
            break
        kept.append(event)
        used += len(line) + 1
    if not kept and events:
        kept.append(events[0])  # always keep the most recent, even if over budget
    kept.reverse()  # chronological for the prompt

    sections = []
    if memories:
        sections.append("Relevant prior context:\n" + memory_text)
    rendered = "\n".join(_render_event(e) for e in kept) if kept else "(no events in window)"
    sections.append("Events:\n" + rendered)
    prompt = "\n\n".join(sections)

    context_ref = "ctx_" + hashlib.sha256(
        (prompt + settings.model_reasoning).encode()
    ).hexdigest()[:16]
    return AssembledContext(events=kept, memories=memories, prompt=prompt, context_ref=context_ref)
