"""World News connector — read-only client to the self-hosted world-news GraphQL gateway.

The app is currently a development SKELETON: its GraphQL `QueryRoot` only exposes `hello`, with no
articles yet. So this connector reports service status (a placeholder to flesh out when the app
grows real resolvers like `articles`/`headlines`). Egress-guarded like every connector.
"""

from __future__ import annotations

import json
from typing import Any

from jarvis.config import get_settings
from jarvis.security.egress import allowed, guarded_request


def _base() -> str:
    return get_settings().world_news_url.rstrip("/")


def _host() -> str:
    return _base().split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]


def _query(graphql: str, *, timeout: float = 6.0) -> dict[str, Any]:
    if not _base():
        raise ValueError("world_news_url not configured")
    if not allowed(_host()):
        raise ValueError(f"egress to {_host()} not allowlisted")
    body = json.dumps({"query": graphql}).encode()
    resp = guarded_request(f"{_base()}/graphql", data=body,
                           headers={"Content-Type": "application/json"}, timeout=timeout)
    return json.loads(resp.read())


def hello() -> str:
    """The gateway's stub greeting — the only field the skeleton exposes today."""
    return str(_query("{ hello }").get("data", {}).get("hello", ""))


def reachable() -> bool:
    try:
        return bool(hello())
    except Exception:  # noqa: BLE001 — any error → unreachable
        return False
