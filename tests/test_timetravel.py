"""Backlog #5 unit: in-memory state reconstruction fold (pure _apply)."""

from __future__ import annotations

from jarvis.state.timetravel import _apply


def _ev(etype: str, entity: str, severity: str = "info", **payload):
    return {"type": etype, "entity_ref": entity, "severity": severity, "payload": payload}


def test_lifecycle_events_drive_status() -> None:
    state: dict = {}
    _apply(state, _ev("container.started", "container:nginx"))
    assert state["container:nginx"]["status"] == "running"
    _apply(state, _ev("container.died", "container:nginx", "warning", exit_code=137))
    assert state["container:nginx"]["status"] == "exited"
    assert state["container:nginx"]["attrs"]["exit_code"] == 137


def test_signal_events_update_attrs_not_status() -> None:
    state: dict = {}
    _apply(state, _ev("container.started", "container:db"))
    _apply(state, _ev("container.cpu_high", "container:db"))
    assert state["container:db"]["status"] == "running"  # lifecycle unchanged
    assert state["container:db"]["attrs"]["cpu_status"] == "high"


def test_non_container_and_no_entity_ignored() -> None:
    state: dict = {}
    _apply(state, _ev("inference.completed", "model:qwen"))  # not container.*
    _apply(state, {"type": "container.started", "entity_ref": None, "severity": "info",
                   "payload": {}})
    assert state == {}
