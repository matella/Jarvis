"""Wave 2 — code syntax validation + the coder's one-shot self-correction (mocked model)."""

from __future__ import annotations

from jarvis.agents import conversation as convo
from jarvis.agents.code_validation import extract_code_blocks, syntax_issues, validate_blocks


def test_extract_code_blocks_finds_labelled_fences() -> None:
    md = "plan\n```python\nprint(1)\n```\nand\n```json\n{\"a\": 1}\n```\n"
    blocks = extract_code_blocks(md)
    assert [lang for lang, _ in blocks] == ["python", "json"]


def test_validate_blocks_flags_bad_python_and_json() -> None:
    assert validate_blocks([("python", "def f(:\n  pass")])  # syntax error → non-empty
    assert validate_blocks([("json", "{not valid}")])
    assert not validate_blocks([("python", "x = 1\n")])      # valid → empty
    assert not validate_blocks([("json", '{"a": 1}')])


def test_validate_blocks_skips_unknown_languages() -> None:
    # We only flag what we can statically prove wrong; bash/unlabelled are left alone.
    assert not validate_blocks([("bash", "rm -rf (((")])
    assert not validate_blocks([("", "this is prose")])


def test_syntax_issues_end_to_end() -> None:
    assert syntax_issues("```python\nreturn (\n```") != []
    assert syntax_issues("```python\nreturn 1\n```") == []


def test_code_answer_retries_once_on_syntax_error(monkeypatch) -> None:
    calls: list[str] = []
    replies = iter([
        "plan\n```python\ndef f(:\n  pass\n```",   # broken first
        "plan\n```python\ndef f():\n    pass\n```",  # fixed second
    ])

    def fake_chat(role, messages, **kwargs):
        calls.append(messages[0]["content"])
        return {"message": {"content": next(replies)}}

    monkeypatch.setattr("jarvis.models.scheduler.chat", fake_chat)
    out = convo._code_answer("", "", "write a no-op function", facts="")
    assert len(calls) == 2                                   # re-asked exactly once
    assert "syntax errors" in calls[1]                       # error fed back into the retry
    assert "def f():" in out.message                          # corrected answer returned


def test_code_answer_no_retry_when_valid(monkeypatch) -> None:
    calls: list[str] = []

    def fake_chat(role, messages, **kwargs):
        calls.append(messages[0]["content"])
        return {"message": {"content": "```python\nprint('ok')\n```"}}

    monkeypatch.setattr("jarvis.models.scheduler.chat", fake_chat)
    convo._code_answer("", "", "print ok", facts="")
    assert len(calls) == 1                                    # valid first time → single inference
