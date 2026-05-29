"""Docker events → Jarvis events.

Streams the remote daemon's container events over the SSH docker context (subprocess),
maps the meaningful ones to `Event`s, and publishes them to the Redis stream. The Docker
stream is a firehose dominated by `exec_*` healthcheck churn, so `map_event` allowlists
real lifecycle actions and drops everything else (CLAUDE.md: resist low-signal events).
"""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Iterator
from datetime import UTC, datetime

from jarvis import ids
from jarvis.config import get_settings
from jarvis.events.models import Event, Severity
from jarvis.events.stream import get_redis, publish_event

# Docker Action -> (event type, severity). Anything not here (exec_create/start/die,
# attach, top, …) is dropped as low-signal.
_ACTION_MAP: dict[str, tuple[str, Severity]] = {
    "start": ("container.started", Severity.info),
    "restart": ("container.restarted", Severity.info),
    "die": ("container.died", Severity.warning),
    "stop": ("container.stopped", Severity.info),
    "kill": ("container.killed", Severity.warning),
    "oom": ("container.oom_killed", Severity.critical),
    "destroy": ("container.destroyed", Severity.info),
    "create": ("container.created", Severity.debug),
    "pause": ("container.paused", Severity.info),
    "unpause": ("container.unpaused", Severity.info),
}


def _occurred_at(raw: dict) -> datetime:
    nano = raw.get("timeNano")
    if nano:
        return datetime.fromtimestamp(nano / 1e9, tz=UTC)
    secs = raw.get("time")
    if secs:
        return datetime.fromtimestamp(secs, tz=UTC)
    return datetime.now(UTC)


def map_event(raw: dict) -> Event | None:
    """Map a raw Docker event dict to an `Event`, or None if it is not of interest."""
    if raw.get("Type") != "container":
        return None
    action = raw.get("Action", "")
    attrs = raw.get("Actor", {}).get("Attributes", {})
    name = attrs.get("name")
    if not name:
        return None

    if action.startswith("health_status"):
        health = action.split(":", 1)[1].strip() if ":" in action else ""
        event_type = "container.health_changed"
        severity = Severity.info if health == "healthy" else Severity.warning
        extra: dict[str, object] = {"health": health}
    else:
        mapped = _ACTION_MAP.get(action)
        if mapped is None:
            return None
        event_type, severity = mapped
        extra = {}

    payload: dict[str, object] = {
        "action": action,
        "container_id": raw.get("Actor", {}).get("ID"),
        "image": attrs.get("image"),
        **extra,
    }
    if "exitCode" in attrs:
        try:
            payload["exit_code"] = int(attrs["exitCode"])
        except (TypeError, ValueError):
            pass

    return Event(
        type=event_type,
        severity=severity,
        source="docker",
        entity_ref=f"container:{name}",
        occurred_at=_occurred_at(raw),
        payload=payload,
        correlation_id=ids.new_id(ids.CORRELATION),  # each ingested event roots a chain
    )


def stream_docker_events(context: str) -> Iterator[dict]:
    """Yield raw Docker event dicts from `docker events` over the given context."""
    cmd = [
        "docker", "--context", context, "events",
        "--filter", "type=container", "--format", "{{json .}}",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue
    finally:
        proc.terminate()


def run_ingester(*, once: bool = False, context: str | None = None) -> None:
    """Stream Docker events and publish the meaningful ones. Reconnects on stream end."""
    context = context or get_settings().docker_context
    r = get_redis()
    while True:
        for raw in stream_docker_events(context):
            event = map_event(raw)
            if event is None:
                continue
            publish_event(r, event)
            print(f"ingested {event.type} {event.entity_ref} -> {event.id}")
            if once:
                return
        if once:
            return
        time.sleep(1.0)  # daemon/stream dropped — back off and reconnect
