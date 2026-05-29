# Phase 9 — Real-time search + visual capture — detailed spec

> Date: 2026-05-30 · Web RAG (local-first via SearXNG) + screenshot capture for "show me X".

## Decisions
- **SearXNG self-hosted** (a docker-compose service) behind a `SearchProvider` interface
  (swappable for a cloud provider). Results are **untrusted data** — sanitized + framed, cited.
- **Visual capture** via headless Playwright, **egress-allowlisted**, for embed-blocked/external
  sites → an `image` view artifact.

## Components
- **infra:** add a `searxng` service to `docker-compose.yml` (JSON output enabled), on the remote.
- **`search/provider.py`** — `SearchProvider` (`search(query, k) -> results`); `search/searxng.py`
  (`SearxngProvider` via the configured SearXNG URL, through the egress guard).
- **conversation agent capability:** a `web.search` step — agent retrieves, quotes results as
  untrusted data, answers with citations (RAG). `search.performed` events for observability.
- **`search/capture.py`** — `screenshot(url) -> image` via headless Playwright (egress-allowlisted);
  surfaced as an `image` artifact ("show me weather.com").
- **config:** `searxng_url`, search result limit; Playwright as a dev/runtime dep.

## Testing → acceptance
- **Unit:** provider result normalization (mocked SearXNG); citation assembly; egress guard blocks
  non-allowlisted capture/search hosts; injection in results → no ungated action.
- **Integration:** against the SearXNG container, a query returns results; a screenshot of a known
  page yields an image.
- **Live:** "what's the latest on CVE-…?" → cited answer from live search; "show me <site>" → a
  captured image in the console.

## Dependencies
5.5c (egress/sanitize), 6a/6b (agent + image artifact rendering). SearXNG container on the box.
