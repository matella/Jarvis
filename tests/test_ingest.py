"""Unit tests for Docker event mapping and projector logic — no DB/Redis."""

from jarvis.events.models import Severity
from jarvis.ingest.docker_events import map_event
from jarvis.state.projector import status_for_type


def _raw(action: str, name: str = "nginx", **attrs) -> dict:
    return {
        "Type": "container",
        "Action": action,
        "Actor": {"ID": "abc123", "Attributes": {"name": name, "image": "nginx:latest", **attrs}},
        "time": 1780052669,
        "timeNano": 1780052669201395800,
    }


def test_maps_start_to_container_started() -> None:
    event = map_event(_raw("start"))
    assert event is not None
    assert event.type == "container.started"
    assert event.severity is Severity.info
    assert event.entity_ref == "container:nginx"
    assert event.source == "docker"
    assert event.correlation_id.startswith("corr_")


def test_die_carries_exit_code() -> None:
    event = map_event(_raw("die", exitCode="137"))
    assert event is not None
    assert event.type == "container.died"
    assert event.severity is Severity.warning
    assert event.payload["exit_code"] == 137


def test_oom_is_critical() -> None:
    event = map_event(_raw("oom"))
    assert event is not None
    assert event.type == "container.oom_killed"
    assert event.severity is Severity.critical


def test_health_status_unhealthy_maps_to_warning() -> None:
    event = map_event(_raw("health_status: unhealthy"))
    assert event is not None
    assert event.type == "container.health_changed"
    assert event.severity is Severity.warning
    assert event.payload["health"] == "unhealthy"


def test_noise_actions_are_dropped() -> None:
    assert map_event(_raw("exec_create: redis-cli ping")) is None
    assert map_event(_raw("exec_start: redis-cli ping")) is None
    assert map_event(_raw("exec_die")) is None


def test_non_container_and_nameless_dropped() -> None:
    assert map_event({"Type": "network", "Action": "connect"}) is None
    nameless = {"Type": "container", "Action": "start", "Actor": {"ID": "x", "Attributes": {}}}
    assert map_event(nameless) is None


def test_occurred_at_uses_nanos() -> None:
    event = map_event(_raw("start"))
    assert event is not None
    assert event.occurred_at.year == 2026


def test_projector_status_map() -> None:
    assert status_for_type("container.started") == "running"
    assert status_for_type("container.died") == "exited"
    assert status_for_type("container.oom_killed") == "oom_killed"
    # health transitions carry no status change
    assert status_for_type("container.health_changed") is None
    # unknown types are not projected
    assert status_for_type("container.frobnicated") is None
