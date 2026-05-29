"""Ambient-reactor unit tests — trigger policy, loop guard, cooldown. No Redis/model."""

from jarvis.core.reactor import ReactorState, should_react
from jarvis.events.models import Event, Severity, utcnow


def _event(etype: str, source: str, sev: Severity = Severity.warning) -> Event:
    return Event(
        type=etype, severity=sev, source=source, entity_ref="container:a",
        occurred_at=utcnow(), correlation_id="corr_x",
    )


def test_reacts_to_container_down_from_operational_sources() -> None:
    assert should_react(_event("container.died", "docker")) is True
    assert should_react(_event("container.oom_killed", "docker", Severity.critical)) is True


def test_does_not_react_to_jarvis_own_events_loop_guard() -> None:
    # an auto-proposed intent must NOT trigger another reaction
    assert should_react(_event("intent.proposed", "infrastructure_agent")) is False
    assert should_react(_event("incident.correlated", "correlator")) is False
    assert should_react(_event("execution.recorded", "orchestrator")) is False
    # even a 'died' from a non-operational source is ignored
    assert should_react(_event("container.died", "correlator")) is False


def test_does_not_react_to_non_trigger_types() -> None:
    assert should_react(_event("container.started", "docker", Severity.info)) is False
    assert should_react(_event("container.cpu_high", "metrics")) is False


def test_cooldown_per_entity() -> None:
    state = ReactorState(cooldown_s=600)
    assert state.allow("container:a", now=1000.0) is True
    assert state.allow("container:a", now=1200.0) is False  # within cooldown
    assert state.allow("container:a", now=1700.0) is True    # elapsed
    assert state.allow("container:b", now=1200.0) is True    # different entity
