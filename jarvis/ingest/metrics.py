"""Metrics poller — docker stats + GPU → telemetry table + debounced signal events.

Raw samples are a firehose, so they go to the `metrics` table only. The event log receives
just signal events: a threshold crossing (e.g. `container.cpu_high`) with hysteresis, so a
sustained-high container emits ONE event, not one per sample, and a matching `*_normal` on
recovery (CLAUDE.md: resist low-signal events).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from typing import Any

from jarvis import db, ids
from jarvis.config import get_settings
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import emit_event
from jarvis.ingest.metrics_store import insert_samples, prune_older_than

Sample = tuple[str, str, dict[str, Any]]  # (entity, kind, sample)

_gpu_fail_logged: str | None = None  # last GPU-sampling failure already logged (anti-spam)


def _host_cores() -> int:
    """CPU count for host-relative normalization (config override, else autodetect)."""
    return get_settings().host_cpu_cores or os.cpu_count() or 1


def host_relative_cpu(cpuperc: float, cores: int) -> float:
    """`docker stats` CPUPerc is per-core (100% = one full core); divide by cores → % of the host,
    so it matches a host-overall view (e.g. Beszel) and the cpu_high threshold is meaningful."""
    return round(cpuperc / max(cores, 1), 1)

_GPU_QUERY = "index,name,utilization.gpu,memory.used,memory.total,temperature.gpu"
_UNITS = {
    "b": 1, "kb": 1e3, "mb": 1e6, "gb": 1e9, "tb": 1e12,
    "kib": 1024, "mib": 1024**2, "gib": 1024**3, "tib": 1024**4,
}


def _parse_pct(text: str | None) -> float:
    try:
        return float((text or "").strip().rstrip("%").strip())
    except ValueError:
        return 0.0


def _parse_bytes(text: str | None) -> int:
    match = re.match(r"([0-9.]+)\s*([a-zA-Z]+)", (text or "").strip())
    if not match:
        return 0
    return int(float(match.group(1)) * _UNITS.get(match.group(2).lower(), 1))


def _parse_mem_usage(text: str | None) -> tuple[int, int]:
    parts = (text or "").split("/")
    used = _parse_bytes(parts[0]) if parts and parts[0].strip() else 0
    limit = _parse_bytes(parts[1]) if len(parts) > 1 else 0
    return used, limit


def _safe_int(text: Any) -> int:
    try:
        return int(text)
    except (TypeError, ValueError):
        return 0


def sample_docker_stats(context: str) -> list[Sample]:
    proc = subprocess.run(
        ["docker", "--context", context, "stats", "--no-stream", "--format", "{{json .}}"],
        capture_output=True, text=True, timeout=30,
    )
    samples: list[Sample] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = raw.get("Name")
        if not name or name == "--":  # docker emits "--" for transient/unnamed containers
            continue
        used, limit = _parse_mem_usage(raw.get("MemUsage"))
        cpu_core = _parse_pct(raw.get("CPUPerc"))  # docker's per-core %, can exceed 100
        samples.append((
            f"container:{name}", "container",
            {
                "cpu_pct": host_relative_cpu(cpu_core, _host_cores()),  # % of the WHOLE host
                "cpu_pct_core": cpu_core,                              # raw per-core % (reference)
                "mem_pct": _parse_pct(raw.get("MemPerc")),
                "mem_used_bytes": used,
                "mem_limit_bytes": limit,
                "pids": _safe_int(raw.get("PIDs")),
                "net_io": raw.get("NetIO"),
                "block_io": raw.get("BlockIO"),
                "container_id": raw.get("ID"),
            },
        ))
    return samples


def sample_gpu(remote_ssh: str) -> list[Sample]:
    if not remote_ssh:
        return []
    from jarvis.core.remote import ssh_cmd
    proc = subprocess.run(
        ssh_cmd(remote_ssh, f"nvidia-smi --query-gpu={_GPU_QUERY} --format=csv,noheader,nounits"),
        capture_output=True, text=True, timeout=15,
    )
    samples: list[Sample] = []
    for line in proc.stdout.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 6:
            continue
        idx, name, util, mem_used, mem_total, temp = parts[:6]
        try:
            used_mb, total_mb = float(mem_used), float(mem_total)
            samples.append((
                f"gpu:{idx}", "gpu",
                {
                    "name": name,
                    "util_pct": float(util),
                    "mem_used_mb": used_mb,
                    "mem_total_mb": total_mb,
                    "mem_pct": round(used_mb / total_mb * 100, 1) if total_mb else 0.0,
                    "temp_c": float(temp),
                },
            ))
        except ValueError:
            continue
    return samples


def _signal_event(
    event_type: str, entity: str, metric: str, value: float, threshold: float, severity: Severity
) -> Event:
    return Event(
        type=event_type,
        severity=severity,
        source="metrics",
        entity_ref=entity,
        occurred_at=utcnow(),
        payload={"metric": metric, "value": round(value, 2), "threshold": threshold},
        correlation_id=ids.new_id(ids.CORRELATION),
    )


class ThresholdTracker:
    """Debounces threshold crossings: one event on enter-high, one on recovery."""

    def __init__(self) -> None:
        self._high: dict[tuple[str, str], bool] = {}

    def evaluate(
        self, entity: str, metric: str, value: float, threshold: float,
        high_type: str, normal_type: str,
    ) -> Event | None:
        key = (entity, metric)
        was_high = self._high.get(key, False)
        now_high = value >= threshold
        self._high[key] = now_high
        if now_high and not was_high:
            return _signal_event(high_type, entity, metric, value, threshold, Severity.warning)
        if was_high and not now_high:
            return _signal_event(normal_type, entity, metric, value, threshold, Severity.info)
        return None


# (sample value-key, settings threshold attr, base event type). High/normal types and the
# debounce metric key derive from the base, e.g. "container.cpu" -> "container.cpu_high".
_CONTAINER_METRICS = (
    ("cpu_pct", "cpu_high_pct", "container.cpu"),
    ("mem_pct", "mem_high_pct", "container.memory"),
)
_GPU_METRICS = (
    ("util_pct", "gpu_util_high_pct", "gpu.utilization"),
    ("mem_pct", "gpu_mem_high_pct", "gpu.memory"),
    ("temp_c", "gpu_temp_high_c", "gpu.temperature"),
)


def _evaluate_all(
    tracker: ThresholdTracker, containers: list[Sample], gpus: list[Sample]
) -> list[Event]:
    s = get_settings()
    events: list[Event] = []
    for samples, specs in ((containers, _CONTAINER_METRICS), (gpus, _GPU_METRICS)):
        for entity, _kind, sample in samples:
            for value_key, threshold_attr, base in specs:
                value = sample.get(value_key)
                if value is None:  # metric absent from this sample → nothing to evaluate
                    continue
                event = tracker.evaluate(
                    entity, base, value, getattr(s, threshold_attr),
                    f"{base}_high", f"{base}_normal",
                )
                if event:
                    events.append(event)
    return events


def poll_once(tracker: ThresholdTracker) -> dict[str, int]:
    s = get_settings()
    containers: list[Sample] = []
    gpus: list[Sample] = []
    try:
        containers = sample_docker_stats(s.docker_context)
    except Exception as exc:  # noqa: BLE001
        print(f"docker stats failed: {exc}")
    try:
        gpus = sample_gpu(s.remote_ssh)
    except Exception as exc:  # noqa: BLE001 — log once per distinct cause, not every 30s cycle
        global _gpu_fail_logged
        cause = f"{type(exc).__name__}: {exc}"
        if cause != _gpu_fail_logged:
            _gpu_fail_logged = cause
            print(f"gpu sample failed (logged once): {exc}")

    with db.connect(autocommit=True) as conn:
        insert_samples(conn, containers + gpus)
        prune_older_than(conn, s.metrics_retention_hours)

    events = _evaluate_all(tracker, containers, gpus)
    for event in events:
        emit_event(event)
    return {"containers": len(containers), "gpu": len(gpus), "signals": len(events)}


def run_poller(*, once: bool = False, tracker: ThresholdTracker | None = None) -> None:
    tracker = tracker or ThresholdTracker()
    interval = get_settings().metrics_poll_interval_s
    while True:
        result = poll_once(tracker)
        print(
            f"sampled containers={result['containers']} gpu={result['gpu']} "
            f"signals={result['signals']}"
        )
        if once:
            return
        time.sleep(interval)
