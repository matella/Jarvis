"""GitHub connector — Jarvis as an MCP *client* of the hosted GitHub MCP server.

The first MCP-as-client link: instead of hand-rolling the GitHub REST surface, deterministic code
calls the official server's tools (Bearer GITHUB_PAT). The execution boundary holds — *code* picks
the tools and parameters, never a model; MCP is purely a data transport here. Tool names are
resolved dynamically from list_tools so upstream renames degrade to a clear error, not a crash.
Dormant until GITHUB_PAT is set and the host is egress-allowlisted.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from jarvis.config import get_settings
from jarvis.security.egress import allowed


def _host() -> str:
    url = get_settings().github_mcp_url
    return url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]


def configured() -> bool:
    """PAT present + host allowlisted — the connector's enable switch."""
    return bool(get_settings().github_pat) and allowed(_host())


async def _session_call(coro_fn) -> Any:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    s = get_settings()
    headers = {"Authorization": f"Bearer {s.github_pat}"}
    async with streamablehttp_client(s.github_mcp_url, headers=headers) as (r, w, _):
        async with ClientSession(r, w) as sess:
            await sess.initialize()
            return await coro_fn(sess)


def _run(coro_fn) -> Any:
    return asyncio.run(_session_call(coro_fn))


def _parse(result) -> Any:
    text = "".join(c.text for c in result.content if getattr(c, "text", None))
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text


async def _find_tool(sess, candidates: list[str]) -> str | None:
    tools = {t.name for t in (await sess.list_tools()).tools}
    return next((c for c in candidates if c in tools), None)


def notifications(limit: int = 10) -> list[dict[str, Any]] | dict[str, str]:
    """Unread GitHub notifications via the hosted MCP. Returns rows or an {'error': …} dict."""
    async def go(sess):
        name = await _find_tool(sess, ["list_notifications", "get_notifications"])
        if not name:
            return {"error": "no notifications tool on the GitHub MCP server"}
        return _parse(await sess.call_tool(name, {"perPage": limit}))

    try:
        return _run(go)
    except Exception as exc:  # noqa: BLE001 — presenter shows the failure plainly
        return {"error": f"GitHub MCP call failed: {type(exc).__name__}"}


def my_open_prs() -> list[dict[str, Any]] | dict[str, str]:
    """The operator's open pull requests (search across repos)."""
    async def go(sess):
        name = await _find_tool(sess, ["search_pull_requests", "search_issues"])
        if not name:
            return {"error": "no search tool on the GitHub MCP server"}
        return _parse(await sess.call_tool(name, {"query": "is:pr is:open author:@me"}))

    try:
        return _run(go)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"GitHub MCP call failed: {type(exc).__name__}"}
