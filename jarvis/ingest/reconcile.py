"""Container-state reconciliation — heal the projection after missed Docker events.

During every deploy the daemon itself restarts and misses a few seconds of `docker events`
(including its own recreate), so the `state` projection drifts: stale statuses and ghost
`<hash>_name` entities left by compose's rename-before-destroy. This worker periodically compares
reality (`docker ps -a`) with the projection and emits **reconciliation events** —
`container.observed` (status differs) and `container.vanished` (entity no longer exists) — which
the projector applies. The event log stays the source of truth; this never writes `state` directly.
Quiet by design: zero events when nothing diverges.
"""

from __future__ import annotations

import json
import subprocess

from jarvis import db, ids
from jarvis.config import get_settings
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import emit_event

# docker `State` → the projection's status vocabulary.
_DOCKER_STATE = {
    "running": "running",
    "exited": "exited",
    "paused": "paused",
    "created": "created",
    "restarting": "restarting",
    "dead": "exited",
}


def real_containers(context: str) -> dict[str, str]:
    """Reality per `docker ps -a`: {name: status}. Raises on docker failure (caller skips)."""
    proc = subprocess.run(
        ["docker", "--context", context, "ps", "-a", "--format", "{{json .}}"],
        capture_output=True, text=True, timeout=30, check=True,
    )
    out: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        name, state = raw.get("Names", ""), (raw.get("State") or "").lower()
        if name:
            out[name] = _DOCKER_STATE.get(state, state or "unknown")
    return out


def _emit(event_type: str, name: str, **payload) -> None:
    emit_event(Event(
        type=event_type, severity=Severity.info, source="reconcile",
        entity_ref=f"container:{name}", occurred_at=utcnow(),
        payload=payload, correlation_id=ids.new_id(ids.CORRELATION),
    ))


def reconcile_once() -> dict[str, int]:
    """One reconciliation pass. Returns {'observed': n, 'vanished': n} (both 0 when in sync)."""
    try:
        real = real_containers(get_settings().docker_context)
    except Exception:  # noqa: BLE001 — docker briefly unavailable → try again next cycle
        return {"observed": 0, "vanished": 0}
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT entity, status FROM state WHERE kind = 'container'"
        ).fetchall()
        projected = {r["entity"].removeprefix("container:"): r["status"] for r in rows}
    observed = vanished = 0
    for name, status in real.items():
        if projected.get(name) != status:
            _emit("container.observed", name, status=status)
            observed += 1
    for name in projected:
        if name not in real:
            _emit("container.vanished", name)
            vanished += 1
    return {"observed": observed, "vanished": vanished}
