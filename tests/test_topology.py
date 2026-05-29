"""Topology edge-derivation unit tests — synthetic inspect dicts, no docker/DB."""

from jarvis.agents.correlator import _render
from jarvis.events.models import Event, Severity, utcnow
from jarvis.ingest.topology import _build_edges


def _c(name, *, id="", project=None, service=None, depends_on="", network_mode="") -> dict:
    return {
        "name": name, "id": id, "project": project, "service": service,
        "depends_on": depends_on, "network_mode": network_mode,
    }


def test_same_project_edges() -> None:
    inspections = [
        _c("gluetun", project="gluetun", service="gluetun"),
        _c("qbittorrent", project="gluetun", service="qbittorrent"),
        _c("radarr", project="radarr", service="radarr"),
    ]
    edges = _build_edges(inspections)
    assert ("container:gluetun", "container:qbittorrent", "same_project") in edges
    # radarr is alone in its project → no same_project edge
    assert not any(rel == "same_project" and "radarr" in (s + d) for s, d, rel in edges)


def test_depends_on_resolves_service_to_container() -> None:
    inspections = [
        _c("gluetun", id="gid", project="gluetun", service="gluetun"),
        _c("qbittorrent", project="gluetun", service="qbittorrent",
           depends_on="gluetun:service_healthy:false"),
    ]
    edges = _build_edges(inspections)
    assert ("container:qbittorrent", "container:gluetun", "depends_on") in edges


def test_network_mode_resolves_container_id() -> None:
    gid = "e3f95359055724e0e83723cd61a529d7bb306bd1fcde85af3fd8b7403514f433"
    inspections = [
        _c("gluetun", id=gid, project="gluetun", service="gluetun"),
        _c("qbittorrent", project="gluetun", service="qbittorrent",
           network_mode=f"container:{gid}"),
    ]
    edges = _build_edges(inspections)
    assert ("container:qbittorrent", "container:gluetun", "network_mode") in edges


def test_no_self_or_unresolved_edges() -> None:
    inspections = [
        _c("solo", project="solo", service="solo", depends_on="ghost:cond:x",
           network_mode="container:deadbeef"),
    ]
    # ghost service and deadbeef id don't resolve → no edges
    assert _build_edges(inspections) == []


def test_correlator_renders_dependencies() -> None:
    ev = Event(type="container.died", severity=Severity.warning, source="docker",
               entity_ref="container:qbittorrent", occurred_at=utcnow(), correlation_id="corr_x")
    edges = [("container:qbittorrent", "container:gluetun", "network_mode")]
    prompt = _render([ev], edges)
    assert "Known dependencies:" in prompt
    assert "container:qbittorrent network_mode container:gluetun" in prompt
    # no edges → no dependency section
    assert "Known dependencies:" not in _render([ev], [])
