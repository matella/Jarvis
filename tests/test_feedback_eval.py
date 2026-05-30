"""Cross-cutting B unit: eval drift comparison + feedback validation (pure)."""

from __future__ import annotations

import pytest

from jarvis import feedback
from jarvis.eval.harness import compare


def test_compare_no_drift_on_confidence_wobble() -> None:
    # same capability + target, only confidence moved → NOT drift (expected nondeterminism)
    r = compare(
        "int_x",
        original_type="docker.restart_container", original_target={"container": "nginx"},
        original_confidence=0.8,
        replayed_type="docker.restart_container", replayed_target={"container": "nginx"},
        replayed_confidence=0.6,
    )
    assert r.drift is False
    assert r.type_changed is False and r.target_changed is False
    assert r.confidence_delta == -0.2


def test_compare_drift_on_type_change() -> None:
    r = compare(
        "int_y",
        original_type="docker.restart_container", original_target={"container": "nginx"},
        original_confidence=0.8,
        replayed_type="infra.investigate", replayed_target={"container": "nginx"},
        replayed_confidence=0.8,
    )
    assert r.drift is True and r.type_changed is True


def test_compare_drift_on_target_change() -> None:
    r = compare(
        "int_z",
        original_type="docker.restart_container", original_target={"container": "nginx"},
        original_confidence=0.8,
        replayed_type="docker.restart_container", replayed_target={"container": "redis"},
        replayed_confidence=0.8,
    )
    assert r.drift is True and r.target_changed is True


def test_feedback_validation() -> None:
    class _Conn:
        def execute(self, *_a, **_k):
            raise AssertionError("should not reach DB on invalid input")

    with pytest.raises(ValueError, match="target_type"):
        feedback.record(_Conn(), target_type="bogus", target_id="x", rating=1, actor="t")
    with pytest.raises(ValueError, match="rating"):
        feedback.record(_Conn(), target_type="intent", target_id="x", rating=5, actor="t")
