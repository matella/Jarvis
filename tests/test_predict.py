"""Predictive-observability unit tests — slope/projection/debounce. No DB."""

from jarvis.events.models import Event, Severity, utcnow
from jarvis.ingest.predict import TrendTracker, _project, _slope_per_min
from jarvis.notify.notifier import should_notify


def _line(start: float, step: float, n: int = 6, dt_s: float = 60.0) -> list[tuple[float, float]]:
    return [(i * dt_s, start + i * step) for i in range(n)]


def test_slope_sign() -> None:
    assert _slope_per_min(_line(50, 5)) > 0      # rising
    assert _slope_per_min(_line(50, 0)) == 0.0    # flat
    assert _slope_per_min(_line(50, -5)) < 0      # falling


def test_project_rising_within_horizon() -> None:
    # rises 5/min; last sample is 75 → (90-75)/5 = 3 min to cross 90
    eta = _project(_line(50, 5), threshold=90.0, horizon_min=30)
    assert eta is not None and 2 < eta < 4


def test_project_none_cases() -> None:
    assert _project(_line(50, 0), 90.0, 30) is None       # flat → never
    assert _project(_line(50, -5), 90.0, 30) is None       # falling
    assert _project(_line(95, 5), 90.0, 30) is None        # already over threshold
    # rising but too slow to cross within the horizon
    assert _project(_line(10, 0.1), 90.0, 30) is None


def test_trend_tracker_debounces() -> None:
    t = TrendTracker()
    key = ("container:a", "container.memory_trending")
    assert t.started(key, True) is True    # enter trend → emit once
    assert t.started(key, True) is False   # still trending → silent
    assert t.started(key, False) is False  # cleared
    assert t.started(key, True) is True    # re-enters → emit again


def test_notifier_pages_on_trending() -> None:
    ev = Event(type="container.memory_trending", severity=Severity.warning, source="predict",
               entity_ref="container:a", occurred_at=utcnow(), correlation_id="corr_x")
    assert should_notify(ev) is True
