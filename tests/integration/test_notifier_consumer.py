"""P4 notifier integration: a critical event on the spine triggers exactly one notification."""

from __future__ import annotations

import pytest
import redis as redis_lib

from jarvis import ids
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import ensure_group, publish_event
from jarvis.notify import notifier

pytestmark = pytest.mark.integration


def test_critical_event_notifies_once(redis_client: redis_lib.Redis, monkeypatch) -> None:
    sent: list[tuple] = []
    monkeypatch.setattr(notifier, "send", lambda **kw: sent.append((kw["title"], kw["severity"])))

    suffix = ids.new_id("t").split("_")[1]
    stream = f"jarvis:test:notif:{suffix}"
    group = "jarvis:test:notifier"
    ensure_group(redis_client, stream, group, start_id="0")
    state = notifier.NotifierState(cooldown_s=300)

    crit = Event(type="container.oom_killed", severity=Severity.critical, source="docker",
                 entity_ref=f"container:itest-{suffix}", occurred_at=utcnow(),
                 correlation_id=ids.new_id(ids.CORRELATION))
    info = Event(type="container.started", severity=Severity.info, source="docker",
                 entity_ref=f"container:itest-{suffix}", occurred_at=utcnow(),
                 correlation_id=ids.new_id(ids.CORRELATION))
    try:
        publish_event(redis_client, crit, stream=stream, maxlen=1000)
        publish_event(redis_client, info, stream=stream, maxlen=1000)

        consumer = "test-notifier"
        total = 0
        for _ in range(3):
            total += notifier.process_batch(
                redis_client, stream=stream, group=group, consumer=consumer, state=state,
                block_ms=100,
            )

        assert total == 1                      # only the critical event notified
        assert sent == [("CRITICAL: container.oom_killed", "critical")]
        assert redis_client.xpending(stream, group)["pending"] == 0  # both acked
    finally:
        redis_client.delete(stream)
