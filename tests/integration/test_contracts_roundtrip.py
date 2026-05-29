"""M1 acceptance: causal chain round-trip + vector memory similarity.

Marked `integration`; skipped automatically when the DB is unreachable (see conftest).
"""

from __future__ import annotations

import psycopg
import pytest

from jarvis import ids
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.repository import get_event, insert_event
from jarvis.intents.models import Execution, ExecutionOutcome, Intent, IntentReasoning
from jarvis.intents.repository import (
    get_executions_for_intent,
    get_intent,
    insert_execution,
    insert_intent,
)
from jarvis.memory.store import MemoryRecord, PgVectorMemoryStore

pytestmark = pytest.mark.integration

DIM = 768


def _unit_vector(*nonzero: tuple[int, float]) -> list[float]:
    vec = [0.0] * DIM
    for index, value in nonzero:
        vec[index] = value
    return vec


def test_event_intent_execution_share_correlation_id(db_conn: psycopg.Connection) -> None:
    corr = ids.new_id(ids.CORRELATION)
    try:
        event = Event(
            type="container.restarted",
            severity=Severity.warning,
            source="docker",
            entity_ref="container:nginx",
            occurred_at=utcnow(),
            payload={"exit_code": 137},
            correlation_id=corr,
        )
        insert_event(db_conn, event)

        intent = Intent(
            type="docker.restart_container",
            target={"container": "nginx"},
            reasoning=IntentReasoning(
                summary="Container unhealthy after repeated failures",
                confidence=0.91,
                risk="low",
                reversible=True,
            ),
            requested_by="infrastructure_agent",
            context_ref=ids.new_id(ids.CONTEXT),
            requires_approval=False,
            correlation_id=corr,
            causation_id=event.id,  # caused by the event
        )
        insert_intent(db_conn, intent)

        execution = Execution(
            intent_id=intent.intent_id,
            outcome=ExecutionOutcome.success,
            before_state={"status": "unhealthy"},
            after_state={"status": "running"},
            correlation_id=corr,
            causation_id=intent.intent_id,  # caused by the intent
        )
        insert_execution(db_conn, execution)

        # Round-trip every row and confirm the causal chain.
        fetched_event = get_event(db_conn, event.id)
        fetched_intent = get_intent(db_conn, intent.intent_id)
        fetched_execs = get_executions_for_intent(db_conn, intent.intent_id)

        assert fetched_event is not None and fetched_event.payload["exit_code"] == 137
        assert fetched_intent is not None
        assert fetched_intent.reasoning.confidence == pytest.approx(0.91)
        assert fetched_intent.causation_id == event.id
        assert len(fetched_execs) == 1
        assert fetched_execs[0].causation_id == intent.intent_id
        assert fetched_execs[0].after_state == {"status": "running"}

        # The whole chain is joined by one correlation_id.
        assert {fetched_event.correlation_id, fetched_intent.correlation_id,
                fetched_execs[0].correlation_id} == {corr}
    finally:
        db_conn.execute("DELETE FROM executions WHERE correlation_id = %s", (corr,))
        db_conn.execute("DELETE FROM intents WHERE correlation_id = %s", (corr,))
        db_conn.execute("DELETE FROM events WHERE correlation_id = %s", (corr,))


def test_memory_roundtrip_and_similarity(db_conn: psycopg.Connection) -> None:
    store = PgVectorMemoryStore(dim=DIM)
    near = MemoryRecord(kind="test_mem", content="oom incident",
                        embedding=_unit_vector((0, 1.0)))
    far = MemoryRecord(kind="test_mem", content="unrelated note",
                       embedding=_unit_vector((400, 1.0)))
    try:
        store.add(near)
        store.add(far)

        query = _unit_vector((0, 0.9), (1, 0.1))  # closest to `near`
        results = store.search(query, k=2, kind="test_mem")

        assert len(results) == 2
        top_record, top_distance = results[0]
        assert top_record.id == near.id
        assert top_record.content == "oom incident"
        assert len(top_record.embedding) == DIM
        # Cosine distance: nearer record is strictly closer.
        assert top_distance < results[1][1]
    finally:
        db_conn.execute("DELETE FROM memory WHERE id = ANY(%s)", ([near.id, far.id],))
