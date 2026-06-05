"""Behavioral eval suite — the 100 example use-cases must route as expected (GPU-free guard)."""

from __future__ import annotations

from jarvis.eval.behavior import failures, run, score
from jarvis.eval.cases import CASES


def test_suite_has_at_least_100_cases() -> None:
    assert len(CASES) >= 100


def test_every_case_routes_as_expected() -> None:
    results = run()
    bad = [(r.case.utterance, f"expected {r.case.expect}, got {r.got}") for r in failures(results)]
    assert not bad, bad


def test_score_is_a_full_pass() -> None:
    assert score(run())["pass_rate"] == 1.0


def test_coverage_spans_every_capability() -> None:
    tags = {t for c in CASES for t in c.tags}
    for need in ("coding", "knowledge", "weather", "tasks", "notes", "mail", "calendar",
                 "recipes", "documents", "research", "search", "memory", "reminder", "ops", "meta"):
        assert need in tags, f"no eval coverage for {need}"


def test_coding_questions_never_hit_a_presenter() -> None:
    # The core guard: a coding/knowledge ask must reach the model, not a 'show my X' presenter.
    results = run()
    for r in results:
        if "coding" in r.case.tags or "knowledge" in r.case.tags:
            assert r.got == "llm", (r.case.utterance, r.got)
