"""Boundary-contract unit tests — no DB required."""

import pytest
from pydantic import ValidationError

from jarvis import ids
from jarvis.events.models import Event, Severity, utcnow
from jarvis.intents.models import (
    Execution,
    Intent,
    IntentReasoning,
    IntentStatus,
)
from jarvis.memory.store import MemoryRecord, PgVectorMemoryStore


def test_new_id_has_prefix_and_is_unique() -> None:
    a = ids.new_id(ids.EVENT)
    b = ids.new_id(ids.EVENT)
    assert a.startswith("evt_") and b.startswith("evt_")
    assert a != b


def test_event_type_must_be_entity_verb() -> None:
    Event(type="container.restarted", severity=Severity.info, source="docker",
          occurred_at=utcnow(), correlation_id="corr_x")
    with pytest.raises(ValidationError):
        Event(type="not-an-entity-verb", severity=Severity.info, source="docker",
              occurred_at=utcnow(), correlation_id="corr_x")


def test_event_rejects_unknown_severity() -> None:
    with pytest.raises(ValidationError):
        Event(type="container.restarted", severity="catastrophic", source="docker",
              occurred_at=utcnow(), correlation_id="corr_x")


def test_intent_confidence_is_bounded() -> None:
    IntentReasoning(summary="ok", confidence=0.5, risk="low", reversible=True)
    with pytest.raises(ValidationError):
        IntentReasoning(summary="too sure", confidence=1.5, risk="low", reversible=True)


def test_boundary_objects_default_schema_version_to_one() -> None:
    reasoning = IntentReasoning(summary="s", confidence=0.9, risk="low", reversible=True)
    intent = Intent(type="docker.restart_container", reasoning=reasoning,
                    requested_by="infrastructure_agent", correlation_id="corr_x")
    execution = Execution(intent_id=intent.intent_id, correlation_id="corr_x")
    event = Event(type="container.restarted", severity=Severity.info, source="docker",
                  occurred_at=utcnow(), correlation_id="corr_x")
    assert event.schema_version == intent.schema_version == execution.schema_version == 1
    assert intent.status is IntentStatus.proposed
    assert intent.requires_approval is True


def test_memory_store_rejects_wrong_dimension() -> None:
    # conn_factory must never be called — validation happens first.
    def explode():  # pragma: no cover - asserts it is not reached
        raise AssertionError("conn_factory should not be called on a bad embedding")

    store = PgVectorMemoryStore(conn_factory=explode, dim=768)
    record = MemoryRecord(kind="note", content="x", embedding=[0.0] * 5)
    with pytest.raises(ValueError, match="expected 768"):
        store.add(record)
