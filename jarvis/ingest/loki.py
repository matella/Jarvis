"""Loki ingest — turn log-rate spikes into spine events that correlation can use.

Logs unlock incidents that metrics alone miss (a flood of errors before a crash). We run configured
LogQL count queries; when a query's count crosses the threshold, we emit a `log.spike` event
(parsing is pure; fetching is egress-guarded). The event flows through the normal spine, so the
correlator can fold a log spike into an incident alongside container/metric signals.
"""

from __future__ import annotations

import json
import time
from urllib.parse import urlencode

from jarvis import ids
from jarvis.config import get_settings
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import emit_event
from jarvis.security.egress import check_url, guarded_request


def parse_count(payload: dict) -> int:
    """Sum the values of a Loki instant-query vector result (a count_over_time). Pure."""
    if payload.get("status") != "success":
        return 0
    total = 0.0
    for item in payload.get("data", {}).get("result", []):
        value = item.get("value")  # vector: [ts, "count"]
        if value and len(value) >= 2:
            try:
                total += float(value[1])
            except (TypeError, ValueError):
                continue
    return int(total)


def detect_spike(count: int, threshold: int) -> bool:
    return count >= threshold


def _spike_event(query: str, count: int) -> Event:
    return Event(
        type="log.spike", severity=Severity.warning, source="loki",
        entity_ref=f"logs:{query[:60]}", occurred_at=utcnow(),
        payload={"query": query, "count": count},
        correlation_id=ids.new_id(ids.CORRELATION),
    )


def scan_once() -> int:
    """Run each log query; emit a log.spike for any over threshold. Returns spikes emitted."""
    s = get_settings()
    if not s.loki_url or not s.loki_queries:
        return 0
    base = s.loki_url.rstrip("/")
    spikes = 0
    for query in s.loki_queries:
        url = f"{base}/loki/api/v1/query?{urlencode({'query': query})}"
        try:
            check_url(url)
            body = guarded_request(url, timeout=15).read()
            count = parse_count(json.loads(body))
        except Exception as exc:  # noqa: BLE001 — one bad query mustn't stop the rest
            print(f"[loki] {query!r} failed: {exc!r}", flush=True)
            continue
        if detect_spike(count, s.loki_spike_threshold):
            emit_event(_spike_event(query, count))
            spikes += 1
    return spikes


def run_loki(*, once: bool = False) -> None:
    interval = get_settings().observability_interval_s
    while True:
        spikes = scan_once()
        if spikes:
            print(f"[loki] {spikes} log spike(s)", flush=True)
        if once:
            return
        time.sleep(interval)
