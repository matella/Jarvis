"""Answer-quality eval core — pure grading + aggregation (model/DB injected, no live calls)."""

from __future__ import annotations

from jarvis.eval.quality import (
    Verdict,
    grade_exact,
    judge_prompt,
    parse_verdict,
    run,
    score,
)
from jarvis.eval.quality_cases import QUALITY_CASES, QualityCase


def test_grade_exact_requires_all_substrings() -> None:
    assert grade_exact("the answer is 84", ("84",)).passed
    assert grade_exact("Canberra is the capital", ("canberra",)).passed  # case-insensitive
    bad = grade_exact("Sydney", ("Canberra",))
    assert not bad.passed and "missing" in bad.reason


def test_parse_verdict_tolerant() -> None:
    v = parse_verdict('{"score": 0.9, "passed": true, "reason": "good"}')
    assert v.passed and v.score == 0.9
    assert not parse_verdict("not json").passed  # never raises → failed verdict


def test_judge_prompt_includes_rubric_and_answer() -> None:
    c = QualityCase("Q?", kind="judge", rubric="must say X")
    p = judge_prompt(c, "the answer")
    assert "must say X" in p and "the answer" in p and "Q?" in p


def test_run_grades_exact_and_judge_and_aggregates() -> None:
    cases = [
        QualityCase("2+2?", kind="exact", must_include=("4",)),
        QualityCase("explain X", kind="judge", rubric="explains X"),
    ]
    answers = {"2+2?": "= 4", "explain X": "X is ..."}
    results = run(
        cases,
        respond_fn=lambda u: answers[u],
        judge_fn=lambda c, a: Verdict(1.0, True, "ok"),
    )
    s = score(results)
    assert s["total"] == 2 and s["passed"] == 2 and s["pass_rate"] == 1.0


def test_run_counts_failures() -> None:
    cases = [QualityCase("cap of Australia?", kind="exact", must_include=("Canberra",))]
    results = run(cases, respond_fn=lambda u: "Sydney", judge_fn=lambda c, a: Verdict(0, False))
    assert score(results)["pass_rate"] == 0.0


def test_quality_cases_curated_and_tagged() -> None:
    assert len(QUALITY_CASES) >= 12
    assert {c.kind for c in QUALITY_CASES} == {"exact", "judge"}
    tags = {t for c in QUALITY_CASES for t in c.tags}
    for need in ("math", "coding", "knowledge", "meta"):
        assert need in tags
