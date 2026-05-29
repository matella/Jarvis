"""P5 reactor integration: a container-down event triggers exactly one (mocked) proposal."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import redis as redis_lib

from jarvis import ids
from jarvis.core import reactor
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import ensure_group, publish_event

pytestmark = pytest.mark.integration


def test_container_down_triggers_one_proposal(redis_client: redis_lib.Redis, monkeypatch) -> None:
    # Mock the agent at its source (process_batch imports it locally at call time) so the test
    # doesn't spend real inference; capture what it's asked about.
    import jarvis.agents.infrastructure as infra

    proposed: list[str] = []
    monkeypatch.setattr(
        infra, "propose_intent",
        lambda entity: proposed.append(entity) or SimpleNamespace(type="x", intent_id="int_x"),
    )

    suffix = ids.new_id("t").split("_")[1]
    stream = f"jarvis:test:reactor:{suffix}"
    group = "jarvis:test:reactor"
    ensure_group(redis_client, stream, group, start_id="0")
    state = reactor.ReactorState(cooldown_s=600)
    entity = f"container:itest-{suffix}"

    def mk(etype, source, sev=Severity.warning) -> Event:
        return Event(type=etype, severity=sev, source=source, entity_ref=entity,
                     occurred_at=utcnow(), correlation_id=ids.new_id(ids.CORRELATION))

    try:
        publish_event(redis_client, mk("container.died", "docker"), stream=stream, maxlen=1000)
        # loop-guard: an agent's own event must NOT trigger a reaction
        publish_event(redis_client, mk("intent.proposed", "infrastructure_agent"),
                      stream=stream, maxlen=1000)

        total = 0
        for _ in range(3):
            total += reactor.process_batch(
                redis_client, stream=stream, group=group, consumer="t", state=state, block_ms=100
            )

        assert total == 1
        assert proposed == [entity]  # reacted to the death, not to intent.proposed
        assert redis_client.xpending(stream, group)["pending"] == 0  # both acked
    finally:
        redis_client.delete(stream)
