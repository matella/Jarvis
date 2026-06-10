"""The MCP server: five read-only tools over Jarvis's existing accessors (no new data paths).

Plain functions first (unit-testable without a transport), registered on FastMCP below. Every tool
catches its own failures and returns a short error dict — an MCP client should never see a stack
trace, and a down model/DB must not kill the server.
"""

from __future__ import annotations

from typing import Any

from jarvis import db
from jarvis.config import get_settings


def news(query: str = "", limit: int = 10) -> list[dict[str, Any]] | dict[str, str]:
    """Recent pooled stories, or a pgvector semantic search when `query` is given."""
    from jarvis.news import repository as repo

    limit = max(1, min(int(limit), 25))
    try:
        with db.connect() as conn:
            if query.strip():
                from jarvis.news.embedding import embed_news
                stories = repo.search_stories(conn, embed_news(query.strip()), limit=limit)
            else:
                stories = repo.recent_stories(conn, limit=limit)
            summaries = repo.story_summaries(conn, [s.id for s in stories])
        return [
            {
                "title": s.title,
                "summary": (s.synthesized_body or summaries.get(s.id, ""))[:300],
                "lang": s.lang,
                "independent_sources": s.origin_count,
                "date": s.created_at.date().isoformat() if s.created_at else None,
            }
            for s in stories
        ]
    except Exception as exc:  # noqa: BLE001 — tools report, never raise to the client
        return {"error": f"news unavailable: {type(exc).__name__}"}


def homelab_state() -> list[dict[str, Any]] | dict[str, str]:
    """The current state projection: every tracked entity with its status."""
    try:
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT entity, kind, status, updated_at FROM state ORDER BY entity"
            ).fetchall()
        return [
            {"entity": r["entity"], "kind": r["kind"], "status": r["status"],
             "updated_at": r["updated_at"].isoformat()}
            for r in rows
        ]
    except Exception as exc:  # noqa: BLE001
        return {"error": f"state unavailable: {type(exc).__name__}"}


def recent_events(limit: int = 20) -> list[dict[str, Any]] | dict[str, str]:
    """The latest events on the spine (deploys, incidents, threshold crossings…)."""
    limit = max(1, min(int(limit), 100))
    try:
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT type, severity, entity_ref, occurred_at FROM events "
                "ORDER BY occurred_at DESC LIMIT %s", (limit,),
            ).fetchall()
        return [
            {"type": r["type"], "severity": r["severity"], "entity": r["entity_ref"],
             "at": r["occurred_at"].isoformat()}
            for r in rows
        ]
    except Exception as exc:  # noqa: BLE001
        return {"error": f"events unavailable: {type(exc).__name__}"}


def recall(query: str = "") -> dict[str, Any]:
    """What Jarvis remembers about the operator: durable facts + semantically related memories."""
    out: dict[str, Any] = {"facts": [], "related_memories": []}
    try:
        from jarvis.memory.facts import list_facts
        with db.connect() as conn:
            out["facts"] = [{"key": f.key, "value": f.value} for f in list_facts(conn)]
    except Exception as exc:  # noqa: BLE001
        out["facts_error"] = type(exc).__name__
    if query.strip():
        try:  # semantic memory search — needs the (CPU) embedder; degrade silently without it
            from jarvis.memory.store import PgVectorMemoryStore
            from jarvis.models.router import embed
            hits = PgVectorMemoryStore().search(embed(query.strip()), k=5)
            out["related_memories"] = [
                {"kind": r.kind, "content": r.content[:300]} for r, _d in hits
            ]
        except Exception as exc:  # noqa: BLE001
            out["memories_error"] = type(exc).__name__
    return out


def ask(question: str) -> dict[str, str]:
    """Ask Jarvis itself: run the real conversation pipeline one-shot and return the grounded
    answer. Uses an LLM — slower than the structured tools; degrades to an error message."""
    question = (question or "").strip()
    if not question:
        return {"error": "empty question"}
    try:
        from jarvis.agents import conversation as convo
        from jarvis.conversation.store import start_conversation
        with db.connect(autocommit=True) as conn:
            session = start_conversation(conn, actor="mcp")
            result = convo.respond(conn, session, question)
        return {"answer": result.message, "route": result.route.value}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Jarvis couldn't answer right now: {type(exc).__name__}"}


def build_server():
    """Construct the FastMCP server with the five tools registered."""
    from mcp.server.fastmcp import FastMCP

    s = get_settings()
    srv = FastMCP("jarvis", host="0.0.0.0", port=s.mcp_port,
                  instructions=(
                      "Jarvis — a self-hosted homelab operational-intelligence AI. Read-only "
                      "tools: pooled world news, live homelab state, recent infrastructure "
                      "events, the operator's remembered facts, and jarvis_ask to get a grounded "
                      "answer from Jarvis itself."))
    srv.tool(name="jarvis_news",
             description="Recent AI-pooled world news, or semantic search with `query`.")(news)
    srv.tool(name="jarvis_homelab_state",
             description="Current status of every tracked homelab container/service.",
             )(homelab_state)
    srv.tool(name="jarvis_recent_events",
             description="Latest events on the homelab event spine.")(recent_events)
    srv.tool(name="jarvis_recall",
             description="Facts Jarvis remembers about the operator (+ semantic memory search).",
             )(recall)
    srv.tool(name="jarvis_ask",
             description="Ask Jarvis a question; runs its reasoning pipeline (slower).")(ask)
    return srv


def main() -> None:
    build_server().run(transport="streamable-http")


if __name__ == "__main__":
    main()
