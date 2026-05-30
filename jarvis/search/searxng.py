"""SearXNG-backed provider — local-first web search via the JSON API, through the egress guard.

Every result field is `sanitize()`d before it leaves this module: a search result is untrusted
external content. Parsing is split from fetching so it's unit-testable on a recorded JSON blob.
"""

from __future__ import annotations

import json
from urllib.parse import urlencode

from jarvis.config import get_settings
from jarvis.search.provider import SearchResult
from jarvis.security.egress import check_url, guarded_request
from jarvis.security.sanitize import sanitize


def normalize(payload: dict, *, k: int) -> list[SearchResult]:
    """Turn a SearXNG JSON response into sanitized SearchResults. Pure — no I/O."""
    out: list[SearchResult] = []
    for r in payload.get("results", [])[:k]:
        url = str(r.get("url", ""))
        if not url:
            continue
        out.append(SearchResult(
            title=sanitize(str(r.get("title", ""))),
            url=url,  # a URL is structural, not prose; kept verbatim for citation/click
            snippet=sanitize(str(r.get("content", "")))[:500],
            engine=str(r.get("engine", "")),
        ))
    return out


class SearxngProvider:
    name = "searxng"

    def search(self, query: str, *, k: int = 5) -> list[SearchResult]:
        s = get_settings()
        if not s.searxng_url:
            raise RuntimeError("searxng_url not configured")
        base = s.searxng_url.rstrip("/")
        url = f"{base}/search?{urlencode({'q': query, 'format': 'json'})}"
        check_url(url)  # egress allowlist (also enforced inside guarded_request)
        body = guarded_request(url, timeout=15).read()
        return normalize(json.loads(body), k=k)


def get_provider() -> SearxngProvider:
    return SearxngProvider()
