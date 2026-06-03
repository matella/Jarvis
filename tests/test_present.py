"""Generic presenter — auto_artifact wraps anything; present picks format + falls back. No DB."""

from __future__ import annotations

import json

from jarvis.present import auto_artifact, present


def test_auto_artifact_wraps_any_shape() -> None:
    a = auto_artifact("Torrents", [{"name": "x", "pct": 50}])
    assert a.kind == "auto" and a.title == "Torrents"
    assert a.data == {"value": [{"name": "x", "pct": 50}]}
    assert auto_artifact("n", 42).data == {"value": 42}          # scalar
    assert auto_artifact("s", "hello").data == {"value": "hello"}  # string
    assert auto_artifact("", None).title == "Result"             # default title


def _chat(payload: dict):
    def chat(role, messages, **kwargs):
        return {"message": {"content": json.dumps(payload)}}
    return chat


def test_present_markdown_choice() -> None:
    a = present({"x": 1}, request="explain it",
                chat_fn=_chat({"title": "Why", "kind": "markdown", "summary": "Because reasons."}))
    assert a.kind == "markdown" and a.title == "Why" and a.data["text"] == "Because reasons."


def test_present_auto_choice_passes_data_through() -> None:
    a = present([1, 2, 3], request="show", chat_fn=_chat({"title": "Series", "kind": "auto"}))
    assert a.kind == "auto" and a.title == "Series" and a.data == {"value": [1, 2, 3]}


def test_present_falls_back_to_auto_on_garbage() -> None:
    def chat(role, messages, **kwargs):
        return {"message": {"content": "not json at all"}}
    a = present([1, 2], request="show", title="Nums", chat_fn=chat)
    assert a.kind == "auto" and a.title == "Nums" and a.data == {"value": [1, 2]}


def test_present_passes_format_schema() -> None:
    seen: dict = {}

    def chat(role, messages, **kwargs):
        seen.update(kwargs)
        return {"message": {"content": json.dumps({"kind": "auto"})}}
    present({"a": 1}, request="show", chat_fn=chat)
    assert seen.get("format") is not None  # grammar-constrained kind selection
