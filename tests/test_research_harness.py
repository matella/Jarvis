"""Deep-research harness — control flow, caps, dedupe, partial-on-failure. No Ollama/network."""

from __future__ import annotations

import json

import jarvis.research.tools  # noqa: F401 — registers research.run for the gating assertion
from jarvis.research.harness import run_harness
from jarvis.research.models import ResearchDepth, ResearchStatus
from jarvis.search.provider import SearchResult
from jarvis.tools.registry import get_tool


def _chat_factory(plan_terms: list[str], report: str = "# Report [1]"):
    calls: list[dict] = []

    def chat(role, messages, **kwargs):
        calls.append({"messages": messages, "kwargs": kwargs})
        # The plan call passes a `format` schema; the synthesize call does not.
        if kwargs.get("format") is not None:
            return {"message": {"content": json.dumps(
                {"sub_questions": ["sq1"], "search_terms": plan_terms})}}
        return {"message": {"content": report}}

    chat.calls = calls  # type: ignore[attr-defined]
    return chat


def _search_factory(per_term: dict[str, list[SearchResult]]):
    def search(term, *, k):
        return per_term.get(term, [])[:k]
    return search


def test_happy_path_plan_search_synthesize() -> None:
    chat = _chat_factory(["term a", "term b"])
    search = _search_factory({
        "term a": [SearchResult("A", "http://a", "snip a")],
        "term b": [SearchResult("B", "http://b", "snip b")],
    })
    run = run_harness("why X?", depth=ResearchDepth.quick, chat_fn=chat, search_fn=search)
    assert run.status is ResearchStatus.done
    assert [s.url for s in run.sources] == ["http://a", "http://b"]
    assert run.report_md.startswith("# Report")
    assert run.cost == {"inferences": 2, "sources": 2}  # exactly two inferences — no loop
    # exactly one plan call (with format) + one synthesize call (without)
    assert sum(1 for c in chat.calls if c["kwargs"].get("format")) == 1
    assert sum(1 for c in chat.calls if not c["kwargs"].get("format")) == 1


def test_dedupes_sources_and_respects_max() -> None:
    chat = _chat_factory(["t1", "t2", "t3"])
    dup = SearchResult("D", "http://dup", "x")
    search = _search_factory({
        "t1": [dup, SearchResult("1", "http://1", "")],
        "t2": [dup, SearchResult("2", "http://2", "")],
        "t3": [SearchResult(str(i), f"http://x{i}", "") for i in range(10)],
    })
    run = run_harness("q", depth=ResearchDepth.quick, chat_fn=chat, search_fn=search)
    urls = [s.url for s in run.sources]
    assert urls.count("http://dup") == 1               # deduped across terms
    assert len(run.sources) <= 6                        # quick cap = 6 sources


def test_no_sources_is_partial_not_failure() -> None:
    chat = _chat_factory(["t1"])
    run = run_harness("q", chat_fn=chat, search_fn=_search_factory({}))
    assert run.status is ResearchStatus.partial
    assert run.cost["sources"] == 0
    # synthesis is skipped when there are no sources → only the plan inference ran
    assert run.cost["inferences"] == 1


def test_synthesis_failure_degrades_to_partial() -> None:
    def chat(role, messages, **kwargs):
        if kwargs.get("format") is not None:
            return {"message": {"content": json.dumps({"search_terms": ["t"]})}}
        raise RuntimeError("model down")

    search = _search_factory({"t": [SearchResult("A", "http://a", "s")]})
    run = run_harness("q", chat_fn=chat, search_fn=search)
    assert run.status is ResearchStatus.partial and run.report_md == ""
    assert [s.url for s in run.sources] == ["http://a"]  # sources retained


def test_bad_plan_json_falls_back_to_raw_query() -> None:
    def chat(role, messages, **kwargs):
        if kwargs.get("format") is not None:
            return {"message": {"content": "not json"}}
        return {"message": {"content": "# R"}}

    captured: list[str] = []

    def search(term, *, k):
        captured.append(term)
        return [SearchResult("A", "http://a", "")]

    run = run_harness("my question", chat_fn=chat, search_fn=search)
    assert captured == ["my question"]  # fallback searches the raw query
    assert run.status is ResearchStatus.done


def test_research_tool_is_gated() -> None:
    tool = get_tool("research.run")
    assert tool is not None and tool.side_effects is True  # external effect → gated by the agent
