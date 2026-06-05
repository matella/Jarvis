"""100 example use-cases spanning Jarvis's domains — the behavioral regression suite's dataset.

Each case is (utterance, expected fastpath_route label, tags). The label is the DETERMINISTIC route:
- "reminder" / "remember": explicit capture phrasings (focused extraction, no infra).
- "weather": the weather presenter (keyword-detected).
- "present:<src>": a 'show my X' request or a mail question → universal presenter.
- "llm": nothing deterministic fires → the LLM router decides (answer / propose / search / recall).

Why so many "llm": most natural questions (coding, knowledge, homelab ops, recall, task/calendar
*questions* without a show-verb) are SUPPOSED to reach the model. The deterministic suite's job:
prove (a) the explicit phrasings fire, and (b) everything else falls through cleanly — a coding
question must NOT be hijacked by a presenter, a mail question must NOT fall to facts recall.
Cases tagged "gap" document a known limitation worth a future fast-path (e.g. rain≠weather keyword).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvalCase:
    """One example: an utterance and the route label we expect fastpath_route to return."""

    utterance: str
    expect: str           # "reminder" | "remember" | "weather" | "present:<src>" | "llm"
    tags: tuple[str, ...] = field(default_factory=tuple)


def _c(utterance: str, expect: str, *tags: str) -> EvalCase:
    return EvalCase(utterance=utterance, expect=expect, tags=tuple(tags))


CASES: list[EvalCase] = [
    # ── Coding: must fall through to the LLM (router/coder model), never a presenter ──
    _c("How do I reverse a string in Python?", "llm", "coding"),
    _c("Write a function to check if a number is prime", "llm", "coding"),
    _c("What's the difference between a list and a tuple in Python?", "llm", "coding"),
    _c("Why am I getting 'IndexError: list index out of range'?", "llm", "coding", "debug"),
    _c("Implement a debounce function in JavaScript", "llm", "coding"),
    _c("Explain how async/await works", "llm", "coding"),
    _c("How do I center a div with flexbox?", "llm", "coding", "css"),
    _c("What does the yield keyword do?", "llm", "coding"),
    _c("Rewrite this SQL to use a JOIN instead of a subquery", "llm", "coding", "sql"),
    _c("How do I parse JSON in Rust?", "llm", "coding"),
    _c("Write a regex that matches an email address", "llm", "coding"),
    _c("What's the time complexity of quicksort?", "llm", "coding", "cs"),
    _c("How do I set up a virtualenv?", "llm", "coding"),
    _c("Help me fix this off-by-one error in my loop", "llm", "coding", "debug"),
    _c("Explain the difference between TCP and UDP", "llm", "coding", "networking"),
    _c("What's the best way to handle exceptions in async Python?", "llm", "coding"),
    _c("Refactor this function to be pure", "llm", "coding"),
    _c("Why is my Docker build so slow?", "llm", "coding", "debug"),
    # ── General knowledge / reasoning → LLM answer ──
    _c("What's the capital of Australia?", "llm", "knowledge"),
    _c("Explain quantum entanglement simply", "llm", "knowledge"),
    _c("Who wrote The Brothers Karamazov?", "llm", "knowledge"),
    _c("How many milliliters are in a cup?", "llm", "knowledge", "conversion"),
    _c("What year did the Berlin Wall fall?", "llm", "knowledge"),
    _c("Summarize the plot of Hamlet", "llm", "knowledge"),
    _c("What's a good substitute for buttermilk?", "llm", "knowledge"),
    _c("Translate 'good morning' into Japanese", "llm", "knowledge"),
    # ── Weather: keyword-detected presenter ──
    _c("What's the weather like?", "weather", "weather"),
    _c("weather in Brussels tomorrow", "weather", "weather"),
    _c("how hot is it in Madrid right now?", "weather", "weather"),
    _c("give me the 5-day forecast", "weather", "weather"),
    _c("quelle est la météo aujourd'hui?", "weather", "weather", "fr"),
    _c("what's the temperature outside?", "weather", "weather"),
    _c("what's the wether like this weekend", "weather", "weather", "typo"),
    # known gaps: no weather keyword → falls to the LLM (documents a future fast-path)
    _c("will it rain tomorrow?", "llm", "weather", "gap"),
    _c("and for this weekend?", "llm", "weather", "followup", "gap"),
    # ── Tasks ──
    _c("show my tasks", "present:tasks", "tasks"),
    _c("list my open tasks", "present:tasks", "tasks"),
    _c("show all tasks", "present:tasks", "tasks"),
    _c("add a task to buy milk", "llm", "tasks", "create"),
    _c("create a high-priority task for the deploy", "llm", "tasks", "create"),
    _c("mark the laundry task as done", "llm", "tasks"),
    _c("what tasks are due this week?", "llm", "tasks", "question"),
    _c("I need to finish the report by Friday", "llm", "tasks"),
    # ── Notes ──
    _c("show my notes", "present:notes", "notes"),
    _c("list my notes", "present:notes", "notes"),
    _c("show my notes tagged work", "present:notes", "notes"),
    _c("what did I note about the project?", "llm", "notes", "question"),
    _c("jot down that the meeting moved to 4pm", "llm", "notes"),
    # ── Mail: a mail question is grabbed even without a show-verb ──
    _c("show my inbox", "present:mail", "mail"),
    _c("what was my last mail about the Lotto?", "present:mail", "mail"),
    _c("any email from the bank?", "present:mail", "mail"),
    _c("check my mail", "present:mail", "mail"),
    _c("do I have any new emails?", "present:mail", "mail"),
    _c("read me my latest email", "present:mail", "mail"),
    _c("mails about the invoice", "present:mail", "mail"),
    _c("show me emails from Amazon", "present:mail", "mail"),
    _c("what's in my inbox?", "present:mail", "mail"),
    _c("summarize my unread mail", "present:mail", "mail"),
    # ── Calendar: 'show' phrasings present; questions fall to LLM ──
    _c("show my calendar", "present:calendar", "calendar"),
    _c("list my events this week", "present:calendar", "calendar"),
    _c("display my agenda", "present:calendar", "calendar"),
    _c("what's on my calendar today?", "llm", "calendar", "question"),
    _c("am I free Friday afternoon?", "llm", "calendar", "question"),
    _c("when's my next meeting?", "llm", "calendar", "question"),
    _c("book a dentist appointment next Tuesday", "llm", "calendar", "create"),
    # ── Recipes ──
    _c("show my recipes", "present:recipes", "recipes"),
    _c("list my recipes", "present:recipes", "recipes"),
    _c("how do I make carbonara?", "llm", "recipes", "knowledge"),
    _c("what can I cook with eggs and spinach?", "llm", "recipes"),
    _c("import this recipe from the URL", "llm", "recipes", "create"),
    # ── Documents ──
    _c("show my documents", "present:documents", "documents"),
    _c("list my docs", "present:documents", "documents"),
    _c("show my reports", "present:documents", "documents"),
    _c("draft a document about the migration plan", "llm", "documents", "create"),
    _c("summarize my latest report", "llm", "documents"),
    # ── Research / web search ──
    _c("show my research", "present:research", "research"),
    _c("list my research reports", "present:research", "research"),
    _c("research the best NAS for a homelab", "llm", "research", "search"),
    _c("look up the latest Python release", "llm", "search"),
    _c("search the web for pgvector benchmarks", "llm", "search"),
    _c("what's the latest news on AI regulation?", "llm", "search"),
    _c("find me reviews of the Framework laptop", "llm", "search"),
    # ── Memory: remember / present / recall ──
    _c("remember my city is Rocourt", "remember", "memory"),
    _c("remember that I prefer metric units", "remember", "memory"),
    _c("note that the garage code is 1234", "remember", "memory"),
    _c("make a note that the spare key is with the neighbour", "remember", "memory"),
    _c("don't forget I'm allergic to penicillin", "remember", "memory"),
    _c("show my memories", "present:memories", "memory"),
    _c("list what you remember about me", "present:memories", "memory"),
    _c("what's my city?", "llm", "memory", "recall"),
    _c("what do you know about me?", "llm", "memory", "recall"),
    # ── Reminders ──
    _c("remind me to call mum at 6pm", "reminder", "reminder"),
    _c("remind me to take out the trash tomorrow", "reminder", "reminder"),
    _c("set a reminder for the meeting at 3", "reminder", "reminder"),
    _c("remind me to submit taxes next week", "reminder", "reminder"),
    _c("remind me about the dentist on Friday", "reminder", "reminder"),
    # ── Homelab ops → LLM proposes a gated intent (never auto-executed) ──
    _c("restart the nginx container", "llm", "ops", "propose"),
    _c("is the database healthy?", "llm", "ops", "question"),
    _c("redeploy the gateway", "llm", "ops", "propose"),
    _c("why did jellyfin crash?", "llm", "ops", "debug"),
    _c("check the redis logs", "llm", "ops"),
    _c("how much disk space is left?", "llm", "ops", "question"),
    _c("are all my containers running?", "llm", "ops", "question"),
    _c("what's using the most memory?", "llm", "ops", "question"),
    # ── Exact compute (#21): pure arithmetic → deterministic, not the model ──
    _c("what is 12 * (3 + 4)?", "math", "math"),
    _c("calculate 2^10", "math", "math"),
    _c("what's 15% of 80", "math", "math"),
    _c("how much is 100 / 8", "math", "math"),
    # numbers in a real question must NOT be grabbed as a calculation:
    _c("what's the time complexity of an O(n^2) sort?", "llm", "math", "coding"),

    # ── Identity / meta → LLM answer ──
    _c("who are you?", "llm", "meta"),
    _c("what can you do?", "llm", "meta"),
    _c("are you Claude or a local model?", "llm", "meta"),
    _c("what's your status?", "llm", "meta"),
]
