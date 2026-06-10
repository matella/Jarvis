"""Actual Budget connector — v1: liveness + dormant-state detection.

Actual's API is a sync protocol (not plain REST), so the full budget client (via `actualpy`)
lands once the operator provides ACTUAL_PASSWORD — until then this mirrors the Orpheus/Spotify
dormant pattern: `reachable()` says the server is up, `authed()` says whether it's enabled, and
the presenter explains exactly what to add. No new dependency until the secret exists.
"""

from __future__ import annotations

import json

from jarvis.config import get_settings
from jarvis.security.egress import allowed, guarded_request


def _base() -> str:
    return get_settings().actual_url.rstrip("/")


def _host() -> str:
    return _base().split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]


def reachable() -> bool:
    """True if the Actual server answers its /info endpoint (no auth needed)."""
    if not allowed(_host()):
        return False
    try:
        resp = guarded_request(f"{_base()}/info", timeout=5.0)
        return bool(json.loads(resp.read()).get("build"))
    except Exception:  # noqa: BLE001 — any error → unreachable
        return False


def authed() -> bool:
    """Whether the operator has provided the server password (enables the full client)."""
    return bool(get_settings().actual_password)
