"""Wave 5 — conservative coding-answer cache (#22): guards, TTL, LRU, and _code_answer reuse."""

from __future__ import annotations

from jarvis.agents import answer_cache as ac
from jarvis.agents import conversation as convo


def test_cacheable_guards() -> None:
    assert ac.cacheable("how do I reverse a string in python")     # self-contained, substantial
    assert not ac.cacheable("fix this")                            # too short + back-reference
    assert not ac.cacheable("why does the error happen")           # "the error" → context-dependent
    assert not ac.cacheable("explain that")                        # demonstrative


def test_get_put_roundtrip_and_normalisation() -> None:
    ac.put("How do I reverse a string in Python?", "use s[::-1]")
    assert ac.get("  how do   I reverse a string in python? ") == "use s[::-1]"  # normalised key
    assert ac.get("a totally different coding question entirely") is None


def test_ttl_expiry(monkeypatch) -> None:
    t = [1000.0]
    monkeypatch.setattr(ac, "_now", lambda: t[0])
    ac.put("how to parse json in python", "json.loads")
    assert ac.get("how to parse json in python") == "json.loads"
    t[0] += ac._TTL_SECONDS + 1
    assert ac.get("how to parse json in python") is None           # expired → dropped


def test_lru_eviction() -> None:
    for i in range(ac._MAX_ENTRIES + 5):
        ac.put(f"coding question number {i} explained", f"answer {i}")
    assert ac.get("coding question number 0 explained") is None    # oldest evicted
    assert ac.get(f"coding question number {ac._MAX_ENTRIES + 4} explained") is not None


def test_non_cacheable_is_never_stored() -> None:
    ac.put("fix this", "some answer")
    assert ac.get("fix this") is None


def test_code_answer_serves_second_call_from_cache(monkeypatch) -> None:
    calls: list[str] = []

    def fake_chat(role, messages, **kwargs):
        calls.append(messages[0]["content"])
        return {"message": {"content": "```python\nprint('hi')\n```"}}

    monkeypatch.setattr("jarvis.models.scheduler.chat", fake_chat)
    q = "how do I print to stdout in python"
    first = convo._code_answer("", "", q, facts="")
    second = convo._code_answer("", "", q, facts="")
    assert first.message == second.message
    assert len(calls) == 1                                          # second call hit the cache
