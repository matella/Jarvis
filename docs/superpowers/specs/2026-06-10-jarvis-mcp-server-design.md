# Jarvis as an MCP server (v1)

**Date:** 2026-06-10 · **Status:** approved, building

## Goal
Expose Jarvis's knowledge to external MCP clients (Claude Desktop, etc.) so the operator can query
news, homelab state, events, memory — and ask Jarvis itself — from any AI tool, over Tailscale.

## Safety scope (the key decision)
**Read-only / advisory tools only.** The MCP server never exposes Intent execution or any action
path; the gated `LLM → Intent → human-approve → deterministic executor` flow stays inside Jarvis.
Hard Rules intact: tools call existing read accessors, no new data paths, local-first (served on the
box, reached via Tailscale).

## Tools (v1)
- `jarvis_news(query?, limit=10)` — recent pooled stories, or pgvector semantic search when a query
  is given (title, summary/synthesis snippet, lang, sources, edition date).
- `jarvis_homelab_state()` — current state projection: containers/services + status (+ flags).
- `jarvis_recent_events(limit=20)` — latest spine events (type, entity, severity, time).
- `jarvis_recall(query)` — operator facts from memory (semantic).
- `jarvis_ask(question)` — run Jarvis's real conversation pipeline one-shot and return the grounded
  answer (uses LLM; slower; degrades gracefully if backends are down).

## Architecture
- `jarvis/mcp/server.py` — official `mcp` Python SDK (FastMCP), **streamable-http** transport,
  bound to `0.0.0.0:8093` (host port mapped; reachable over Tailscale).
- Own process: new compose service `jarvis-mcp` (same image, `python -m jarvis.mcp`), so a hang
  can't affect the daemon/gateway. DB access read-only by construction (only read accessors used).
- Each tool returns compact JSON-able dicts; errors return a short message instead of raising.

## Testing
Unit tests for each tool function with mocked repos (no MCP transport needed). Live verification:
MCP client handshake + a `jarvis_news` call from the box.

## Out of scope (later)
Write/proposal tools (file an Intent for human approval), auth beyond network posture (Tailscale is
the boundary), resources/prompts, voice.
