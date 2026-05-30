"""Home Assistant connector — read (state poll → events) + `ha.set_state` act-Tool (REST → Intent).

Two directions, both behind the boundary. READ: poll the configured watched entities and emit a
`ha.state_changed` event when one actually changes — so Jarvis observes lights/sensors/climate.
ACT: "turn on the office lights" becomes a validated Intent that, only after the gate approves,
calls HA's REST service API. Token from SecretsProvider (`HA_TOKEN`); the HA host is checked
against the egress allowlist. Validation pins the call to a domain/service/entity shape so a model
can't craft an arbitrary request. `rollback=automatic`: toggling a state is reversible.
"""

from __future__ import annotations

import json
import re
from typing import Any

from jarvis import ids
from jarvis.config import get_settings
from jarvis.connectors.base import register_connector
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import emit_event
from jarvis.security.egress import allowed
from jarvis.security.sanitize import sanitize
from jarvis.security.secrets import get_provider
from jarvis.tools.contract import Rollback, Tool
from jarvis.tools.registry import register

_ENTITY_RE = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")  # e.g. light.office
_SERVICE_RE = re.compile(r"^[a-z_]+$")
# Only reversible on/off-style services are allowed through this Tool.
_TOGGLE = {"turn_on": "turn_off", "turn_off": "turn_on", "toggle": "toggle"}


def _require(target: dict[str, Any]) -> tuple[str, str, str]:
    entity = target.get("entity")
    service = target.get("service", "turn_on")
    if not isinstance(entity, str) or not _ENTITY_RE.match(entity):
        raise ValueError(f"invalid HA entity: {target!r}")
    if not isinstance(service, str) or service not in _TOGGLE:
        raise ValueError(f"unsupported HA service (allowed: {sorted(_TOGGLE)}): {service!r}")
    domain = entity.split(".", 1)[0]
    return domain, service, entity


def _call_service(domain: str, service: str, entity: str, *, timeout_s: int) -> dict[str, Any]:
    from jarvis.security.egress import guarded_request

    s = get_settings()
    if not s.ha_base_url:
        raise ValueError("ha_base_url not configured")
    host = s.ha_base_url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
    if not allowed(host):
        raise ValueError(f"egress to {host} not allowlisted")
    token = get_provider().required("HA_TOKEN")
    url = f"{s.ha_base_url}/api/services/{domain}/{service}"
    payload = json.dumps({"entity_id": entity}).encode()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    guarded_request(url, data=payload, headers=headers, timeout=timeout_s).read()
    return {"entity": entity, "service": service}


def _ha_preview(target: dict[str, Any]) -> dict[str, Any]:
    domain, service, entity = _require(target)
    return {"would_call": f"{domain}.{service}", "entity": entity}


def _ha_run(target: dict[str, Any], *, timeout_s: int) -> dict[str, Any]:
    domain, service, entity = _require(target)
    return _call_service(domain, service, entity, timeout_s=timeout_s)


def _ha_revert(target: dict[str, Any]) -> dict[str, Any]:
    domain, service, entity = _require(target)
    inverse = _TOGGLE[service]
    return _call_service(domain, inverse, entity, timeout_s=15)


register(Tool(
    name="ha.set_state",
    version=1,
    permissions=["ha:service"],
    side_effects=True,
    idempotent=True,
    max_retries=1,
    timeout_seconds=15,
    rollback=Rollback.automatic,  # toggling is reversible
    run=_ha_run,
    preview=_ha_preview,
    revert=_ha_revert,
))


# --- HA read-ingest: watched entities → ha.state_changed events -------------------------------

_last_state: dict[str, str] = {}  # entity → last seen state, to emit only on real change


def _fetch_states() -> list[dict[str, Any]]:
    from jarvis.security.egress import guarded_request

    s = get_settings()
    if not s.ha_base_url or not s.ha_watch_entities:
        return []
    host = s.ha_base_url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
    if not allowed(host):
        raise ValueError(f"egress to {host} not allowlisted")
    token = get_provider().required("HA_TOKEN")
    url = f"{s.ha_base_url}/api/states"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = guarded_request(url, headers=headers, timeout=15).read()
    return json.loads(body)


def _changed(entity: str, state: str) -> str | None:
    """Return the previous state if it changed (and record), else None. Pure-ish (module cache)."""
    prev = _last_state.get(entity)
    if prev == state:
        return None
    _last_state[entity] = state
    return prev if prev is not None else ""  # "" = first observation


def poll_states() -> int:
    """Emit ha.state_changed for each watched entity whose state changed. Returns count emitted."""
    s = get_settings()
    watch = set(s.ha_watch_entities)
    emitted = 0
    for item in _fetch_states():
        entity = str(item.get("entity_id", ""))
        if entity not in watch:
            continue
        state = str(item.get("state", ""))
        prev = _changed(entity, state)
        if prev is None:
            continue
        emit_event(Event(
            type="ha.state_changed", severity=Severity.info, source="homeassistant",
            entity_ref=f"ha:{entity}", occurred_at=utcnow(),
            payload={"entity": entity, "from": sanitize(prev), "to": sanitize(state)},
            correlation_id=ids.new_id(ids.CORRELATION),
        ))
        emitted += 1
    return emitted


class HomeAssistantConnector:
    name = "homeassistant"

    def ingest(self, *, once: bool = True) -> int:
        return poll_states()


register_connector(HomeAssistantConnector())
