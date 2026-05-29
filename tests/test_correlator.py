"""Alert-correlator unit tests — clustering/dedup/parse, no model/DB."""

from datetime import timedelta

import pytest

from jarvis.agents.correlator import (
    _analyze,
    _dedup_lines,
    _max_severity,
    cluster,
)
from jarvis.events.models import Event, Severity, utcnow
from jarvis.incidents.models import IncidentAnalysis


def _alert(
    seconds: int, etype="container.died", sev=Severity.warning, entity="container:a"
) -> Event:
    return Event(
        type=etype, severity=sev, source="docker", entity_ref=entity,
        occurred_at=utcnow() + timedelta(seconds=seconds), correlation_id="corr_x",
    )


def test_cluster_splits_on_gap() -> None:
    alerts = [_alert(0), _alert(30), _alert(60), _alert(4000), _alert(4030)]
    clusters = cluster(alerts, gap_s=300)
    assert [len(c) for c in clusters] == [3, 2]  # burst, big gap, burst


def test_cluster_single_burst() -> None:
    alerts = [_alert(0), _alert(60), _alert(120), _alert(180)]
    assert [len(c) for c in cluster(alerts, gap_s=300)] == [4]


def test_dedup_lines_counts_repeats() -> None:
    cl = [
        _alert(0, "container.died", entity="container:a"),
        _alert(1, "container.died", entity="container:a"),
        _alert(2, "container.killed", entity="container:b"),
    ]
    lines = sorted(_dedup_lines(cl))
    assert lines == ["container.died container:a (x2)", "container.killed container:b"]


def test_max_severity() -> None:
    cl = [_alert(0, sev=Severity.warning), _alert(1, sev=Severity.critical),
          _alert(2, sev=Severity.error)]
    assert _max_severity(cl) is Severity.critical


def test_analyze_parses_and_rejects(monkeypatch) -> None:
    import jarvis.agents.correlator as corr

    good = '{"summary": "3 containers died", "root_cause": "oom"}'
    monkeypatch.setattr(corr.router, "chat", lambda *a, **k: {"message": {"content": good}})
    result = _analyze("prompt", "corr_x", "ctx_x")
    assert isinstance(result, IncidentAnalysis)
    assert result.root_cause == "oom"

    monkeypatch.setattr(corr.router, "chat", lambda *a, **k: {"message": {"content": "not json"}})
    with pytest.raises(ValueError, match="schema validation"):
        _analyze("prompt", "corr_x", "ctx_x")
