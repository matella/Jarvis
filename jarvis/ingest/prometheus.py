"""Prometheus ingest — sample PromQL instant queries into the `metrics` table.

Real exporter metrics (node/cAdvisor/GPU) give far sharper correlation than docker stats alone.
Parsing is pure (recorded JSON → samples); fetching goes through the egress guard. Samples land in
`metrics` with kind="prometheus" so the existing trend/correlation machinery can use them.
"""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlencode

from jarvis import db
from jarvis.config import get_settings
from jarvis.ingest.metrics_store import insert_samples
from jarvis.security.egress import check_url, guarded_request

Sample = tuple[str, str, dict[str, Any]]  # (entity, kind, sample)


def _entity_of(metric: dict[str, str]) -> str:
    return (
        metric.get("instance") or metric.get("name") or metric.get("job")
        or metric.get("__name__") or "prometheus"
    )


def parse_instant(payload: dict, query: str) -> list[Sample]:
    """Parse a Prometheus /api/v1/query (vector) response into metric samples. Pure."""
    if payload.get("status") != "success":
        return []
    out: list[Sample] = []
    for item in payload.get("data", {}).get("result", []):
        metric = item.get("metric", {})
        value = item.get("value")  # [timestamp, "stringified float"]
        if not value or len(value) < 2:
            continue
        try:
            v = float(value[1])
        except (TypeError, ValueError):
            continue
        out.append((
            _entity_of(metric), "prometheus",
            {"query": query, "metric": metric.get("__name__", query), "value": v,
             "labels": metric},
        ))
    return out


def scrape_once() -> int:
    """Run every configured query, persist samples. Returns count written."""
    s = get_settings()
    if not s.prometheus_url or not s.prometheus_queries:
        return 0
    base = s.prometheus_url.rstrip("/")
    written = 0
    with db.connect() as conn:
        for query in s.prometheus_queries:
            url = f"{base}/api/v1/query?{urlencode({'query': query})}"
            try:
                check_url(url)
                body = guarded_request(url, timeout=15).read()
                samples = parse_instant(json.loads(body), query)
            except Exception as exc:  # noqa: BLE001 — one bad query mustn't stop the rest
                print(f"[prometheus] {query!r} failed: {exc!r}", flush=True)
                continue
            written += insert_samples(conn, samples)
    return written


def run_prometheus(*, once: bool = False) -> None:
    interval = get_settings().observability_interval_s
    while True:
        count = scrape_once()
        if count:
            print(f"[prometheus] sampled {count} series", flush=True)
        if once:
            return
        time.sleep(interval)
