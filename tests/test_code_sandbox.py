"""Wave 1.2 — execute-to-verify: block selection, failure feedback, gating, _code_answer wiring.

The Docker invocation itself is exercised by an on-box smoke test (needs Docker); here we unit-test
the pure decision logic and the integration via monkeypatching.
"""

from __future__ import annotations

from jarvis.agents import code_sandbox as sb
from jarvis.agents import conversation as convo


def test_runnable_python_picks_longest_self_contained() -> None:
    blocks = [("python", "x=1"), ("python", "for i in range(3):\n    print(i)"), ("bash", "ls")]
    assert sb.runnable_python(blocks) == "for i in range(3):\n    print(i)"


def test_runnable_python_skips_interactive_and_empty() -> None:
    assert sb.runnable_python([("python", "name = input('? ')")]) is None
    assert sb.runnable_python([("python", "   ")]) is None
    assert sb.runnable_python([("bash", "echo hi")]) is None


def test_failure_feedback_only_on_real_errors() -> None:
    assert sb.failure_feedback(sb.RunResult(ran=False)) is None              # skipped → no verdict
    assert sb.failure_feedback(sb.RunResult(ran=True, exit_code=0)) is None  # clean exit → pass
    timed = sb.RunResult(ran=True, exit_code=124, timed_out=True)
    assert "time limit" in sb.failure_feedback(timed)
    boom = sb.RunResult(ran=True, exit_code=1,
                        stderr="Traceback (most recent call last):\nValueError: nope")
    fb = sb.failure_feedback(boom)
    assert fb and "ValueError: nope" in fb


def test_run_python_returns_not_ran_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(sb, "exec_enabled", lambda: False)
    # verify() short-circuits before touching Docker when the feature is off.
    assert sb.verify("```python\nprint(1/0)\n```") is None


def test_verify_skips_when_nothing_runnable(monkeypatch) -> None:
    monkeypatch.setattr(sb, "exec_enabled", lambda: True)
    called = {"ran": False}
    monkeypatch.setattr(sb, "run_python", lambda code: called.__setitem__("ran", True) or
                        sb.RunResult(ran=True))
    assert sb.verify("no code here, just prose") is None
    assert called["ran"] is False  # never invoked the sandbox


def test_code_answer_reasks_on_runtime_failure(monkeypatch) -> None:
    calls: list[str] = []
    replies = iter([
        "```python\nprint(1/0)\n```",          # runs → ZeroDivisionError
        "```python\nprint('fixed')\n```",       # corrected
    ])

    def fake_chat(role, messages, **kwargs):
        calls.append(messages[0]["content"])
        return {"message": {"content": next(replies)}}

    monkeypatch.setattr("jarvis.models.scheduler.chat", fake_chat)
    # Force the sandbox to report a runtime failure on the first answer.
    monkeypatch.setattr(
        "jarvis.agents.code_sandbox.verify",
        lambda md: "When run, the code raised:\nZeroDivisionError: division by zero"
        if "1/0" in md else None,
    )
    out = convo._code_answer("", "", "divide two numbers", facts="")
    assert len(calls) == 2                       # re-asked once with the runtime error
    assert "sandbox it failed" in calls[1]
    assert "fixed" in out.message
