"""Full-pipeline answer-QUALITY eval — runs real questions through Jarvis and grades the answers.

Wave 0's behavior.py pins *routing* (GPU-free, in CI). This pins *correctness*: it drives the actual
`respond()` pipeline against a live model, then grades each answer — exact-match for deterministic
asks (arithmetic), LLM-as-judge against a rubric for open-ended ones (coding, knowledge). Because it
needs a live model + DB it's an ON-DEMAND, on-box gate (`make eval-quality`), not a CI check.

The core (`grade_exact`, `judge_prompt`, `parse_verdict`, `run`, `score`) is pure and injectable, so
it's unit-tested with mocked `respond_fn`/`judge_fn`; `main()` wires the real pipeline + a judge.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

from jarvis.eval.quality_cases import QUALITY_CASES, QualityCase

_PASS_THRESHOLD = 0.7  # judge score at/above this = pass

_JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "number"},
        "passed": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["score", "passed", "reason"],
}


@dataclass(frozen=True)
class Verdict:
    score: float
    passed: bool
    reason: str = ""


@dataclass(frozen=True)
class QualityResult:
    case: QualityCase
    answer: str
    verdict: Verdict


def grade_exact(answer: str, must_include: tuple[str, ...]) -> Verdict:
    """Deterministic grade: every required substring must appear (case-insensitive)."""
    low = answer.lower()
    missing = [s for s in must_include if s.lower() not in low]
    if missing:
        return Verdict(0.0, False, f"missing: {', '.join(missing)}")
    return Verdict(1.0, True, "all required content present")


def judge_prompt(case: QualityCase, answer: str) -> str:
    """The LLM-as-judge prompt: score the answer against the case's rubric."""
    return (
        "You are a strict grader of an AI assistant's answer. Judge ONLY against the rubric.\n\n"
        f"Question: {case.utterance}\n"
        f"Rubric (what a correct answer must do): {case.rubric}\n\n"
        f"Assistant's answer:\n{answer}\n\n"
        "Return ONE JSON object: {\"score\": 0.0-1.0, \"passed\": <score>=0.7>, "
        "\"reason\": <one sentence>}. Be fair but exacting; reward correctness over verbosity."
    )


def parse_verdict(raw: str) -> Verdict:
    """Tolerant parse of the judge JSON → Verdict (unparseable → failed verdict, never raises)."""
    try:
        data = json.loads(raw)
        score = float(data.get("score", 0.0))
        passed = bool(data.get("passed", score >= _PASS_THRESHOLD))
        return Verdict(score, passed, str(data.get("reason", "")))
    except (json.JSONDecodeError, TypeError, ValueError):
        return Verdict(0.0, False, "unparseable judge response")


def run(
    cases: list[QualityCase],
    *,
    respond_fn: Callable[[str], str],
    judge_fn: Callable[[QualityCase, str], Verdict],
) -> list[QualityResult]:
    """Drive each case through respond_fn, grade it (exact or judge), collect results."""
    out: list[QualityResult] = []
    for c in cases:
        answer = respond_fn(c.utterance)
        verdict = (
            grade_exact(answer, c.must_include) if c.kind == "exact" else judge_fn(c, answer)
        )
        out.append(QualityResult(case=c, answer=answer, verdict=verdict))
    return out


def score(results: list[QualityResult]) -> dict[str, float | int]:
    total = len(results)
    passed = sum(1 for r in results if r.verdict.passed)
    mean = round(sum(r.verdict.score for r in results) / total, 4) if total else 0.0
    return {"total": total, "passed": passed, "failed": total - passed,
            "pass_rate": round(passed / total, 4) if total else 0.0, "mean_score": mean}


def _llm_judge(case: QualityCase, answer: str) -> Verdict:
    """Grade with the strong backend (Claude) for reliable scoring; falls back via the scheduler."""
    from jarvis.models.scheduler import Priority
    from jarvis.models.scheduler import chat as sched_chat

    resp = sched_chat(
        "reasoning", [{"role": "user", "content": judge_prompt(case, answer)}],
        priority=Priority.INTERACTIVE, backend="claude", format=_JUDGE_SCHEMA,
    )
    return parse_verdict(str(resp["message"]["content"]))


def main() -> int:
    """`python -m jarvis.eval.quality` (on the box) — run the full pipeline + grade; exit non-zero
    if the pass-rate drops below the threshold."""
    from jarvis.agents.conversation import respond
    from jarvis.conversation.store import start_conversation
    from jarvis.db import connect

    with connect() as conn:
        def respond_fn(utterance: str) -> str:
            session = start_conversation(conn, actor="eval-quality")
            return respond(conn, session, utterance, store=None).message

        results = run(QUALITY_CASES, respond_fn=respond_fn, judge_fn=_llm_judge)

    for r in results:
        mark = "ok  " if r.verdict.passed else "FAIL"
        print(f"{mark} [{r.verdict.score:.2f}] {r.case.utterance}  — {r.verdict.reason}")
    s = score(results)
    print(f"\n{s['passed']}/{s['total']} passed · pass_rate {s['pass_rate'] * 100:.1f}% · "
          f"mean {s['mean_score']:.2f}")
    return 0 if s["pass_rate"] >= _PASS_THRESHOLD else 1


if __name__ == "__main__":
    raise SystemExit(main())
