"""Jellyseerr connector — gated actions: request a title (search → request) + approve a request.

Jellyseerr is the media-request hub (Radarr/Sonarr sit behind it). These are capability-scoped
Tools: the agent can only PROPOSE them; the human gate confirms before they run, audited like any
action. API key via SecretsProvider (`JELLYSEERR_API_KEY`); base URL from config. Search results
come from TMDB (external) → titles are `sanitize()`d before they reach the model.

`jellyseerr.request` resolves a free-text title to a TMDB id and creates the request — the natural
"Jarvis, request Dune: Part Two" flow. `jellyseerr.approve` approves a pending request by id.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from jarvis.config import get_settings
from jarvis.security.sanitize import sanitize
from jarvis.security.secrets import get_provider
from jarvis.tools.contract import Rollback, Tool
from jarvis.tools.registry import register

_REQUESTABLE = {"movie", "tv"}


def _api(method: str, path: str, body: dict | None = None) -> Any:
    """Call the Jellyseerr API with the X-Api-Key header. Raises on non-2xx."""
    s = get_settings()
    if not s.jellyseerr_url:
        raise ValueError("jellyseerr_url not configured")
    base = s.jellyseerr_url.rstrip("/")
    headers = {"X-Api-Key": get_provider().required("JELLYSEERR_API_KEY"),
               "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(  # noqa: S310 — operator-configured internal service + API key
        base + path, data=data, headers=headers, method=method,
    )
    resp = urllib.request.urlopen(req, timeout=15)  # noqa: S310
    raw = resp.read()
    return json.loads(raw) if raw else {}


def _top_match(query: str) -> dict[str, Any] | None:
    """First movie/tv search result for a free-text title (sanitized title for display)."""
    # quote_via=quote → spaces become %20, NOT '+' (Jellyseerr 400s on '+').
    q = urllib.parse.urlencode({"query": query}, quote_via=urllib.parse.quote)
    for r in _api("GET", f"/api/v1/search?{q}").get("results", []):
        if r.get("mediaType") in _REQUESTABLE and r.get("id"):
            return {
                "tmdb_id": int(r["id"]),
                "media_type": str(r["mediaType"]),
                "title": sanitize(str(r.get("title") or r.get("name") or "")),
            }
    return None


# --- jellyseerr.request -----------------------------------------------------------------------

def _require_query(target: dict[str, Any]) -> str:
    q = target.get("query") or target.get("title")
    if not isinstance(q, str) or not q.strip():
        raise ValueError(f"jellyseerr.request needs a 'query' (title): {target!r}")
    return q.strip()


def _request_preview(target: dict[str, Any]) -> dict[str, Any]:
    match = _top_match(_require_query(target))
    return {"would_request": match["title"] if match else None,
            "media_type": match["media_type"] if match else None}


def _request_run(target: dict[str, Any], *, timeout_s: int) -> dict[str, Any]:
    match = _top_match(_require_query(target))
    if match is None:
        raise ValueError(f"no movie/show found for {target.get('query') or target.get('title')!r}")
    body: dict[str, Any] = {"mediaType": match["media_type"], "mediaId": match["tmdb_id"]}
    if match["media_type"] == "tv":
        body["seasons"] = "all"
    _api("POST", "/api/v1/request", body)
    return {"requested": match["title"], "media_type": match["media_type"]}


register(Tool(
    name="jellyseerr.request", version=1, permissions=["jellyseerr:request"],
    side_effects=True, idempotent=False, max_retries=0, timeout_seconds=20,
    rollback=Rollback.none, run=_request_run, preview=_request_preview,
))


# --- jellyseerr.approve -----------------------------------------------------------------------

def _require_request_id(target: dict[str, Any]) -> str:
    rid = target.get("request_id")
    if not (isinstance(rid, (str, int)) and str(rid).isdigit()):
        raise ValueError(f"jellyseerr.approve needs a numeric 'request_id': {target!r}")
    return str(rid)


def _approve_preview(target: dict[str, Any]) -> dict[str, Any]:
    return {"would_approve_request": _require_request_id(target)}


def _approve_run(target: dict[str, Any], *, timeout_s: int) -> dict[str, Any]:
    rid = _require_request_id(target)
    _api("POST", f"/api/v1/request/{rid}/approve")
    return {"approved_request": rid}


register(Tool(
    name="jellyseerr.approve", version=1, permissions=["jellyseerr:approve"],
    side_effects=True, idempotent=True, max_retries=1, timeout_seconds=15,
    rollback=Rollback.none, run=_approve_run, preview=_approve_preview,
))
