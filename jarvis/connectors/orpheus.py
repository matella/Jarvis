"""Orpheus connector — read-only client to the self-hosted Orpheus music server.

The operator's autonomous music system (Node/Fastify, server on :3000 → host :3010). Jarvis presents
what's playing + the active session on demand, via the same egress-guarded path as every connector.
`authed()` reflects whether Spotify is connected — placeholder creds → False (the dormant state), so
the presenter can say "running, but Spotify isn't connected yet" instead of showing an empty card.
"""

from __future__ import annotations

import json
from typing import Any

from jarvis.config import get_settings
from jarvis.security.egress import allowed, guarded_request


def _base() -> str:
    return get_settings().orpheus_api_url.rstrip("/")


def _host() -> str:
    return _base().split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]


def _get(path: str, *, timeout: float = 6.0) -> Any:
    if not _base():
        raise ValueError("orpheus_api_url not configured")
    if not allowed(_host()):
        raise ValueError(f"egress to {_host()} not allowlisted")
    return json.loads(guarded_request(f"{_base()}{path}", timeout=timeout).read())


def reachable() -> bool:
    """True if the Orpheus server answers — a live check for the presenter's failure message."""
    try:
        return _get("/api/health", timeout=4.0).get("status") == "ok"
    except Exception:  # noqa: BLE001 — any error → unreachable
        return False


def authed() -> bool:
    """Whether Spotify is connected. Placeholder creds → False (the dormant state)."""
    try:
        return bool(_get("/api/auth/status", timeout=4.0).get("authenticated"))
    except Exception:  # noqa: BLE001
        return False


def now_playing() -> dict[str, Any]:
    return _get("/api/playback/current")


def active_session() -> dict[str, Any]:
    return _get("/api/sessions/active")
