"""The conversation/executive agent — one inference, one structured TurnResult.

NL + assembled context (recency + entity + vector + playbooks) + recent conversation memory +
a self-describing capability summary → a structured decision: *answer*, or *propose* a gated
Intent. It never executes; proposing routes through the existing M4 gate, and acting only happens
on an explicit confirmation in a later turn (`confirm-to-act`, handled in `respond`). External
content is data, not instructions — the deterministic boundary, not the model, enforces safety.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import psycopg
from pydantic import BaseModel, Field, ValidationError

import jarvis.modules.builtin_tools  # noqa: F401 — register personal-OS module tools before routing
from jarvis import capabilities, ids
from jarvis.config import get_settings
from jarvis.conversation.store import Session, add_message, recent_messages
from jarvis.core.assembly import assemble_context
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import emit_event
from jarvis.intents.models import Intent, IntentReasoning, Risk
from jarvis.intents.repository import insert_intent
from jarvis.memory.facts import facts_block, list_facts, set_fact
from jarvis.present import auto_artifact
from jarvis.tools.registry import ADVISORY_TYPES, get_tool, valid_intent_types
from jarvis.weather import looks_like_weather, weather_view
from jarvis.weather.provider import WeatherUnavailable, extract_location

_WINDOW_HOURS = 24
_AFFIRMATIVE = {"yes", "y", "yes please", "yep", "yeah", "do it", "go ahead", "confirm",
                "approved", "approve", "ok", "okay", "sure", "proceed"}
_NEGATIVE = {"no", "n", "nope", "cancel", "stop", "abort", "don't", "do not", "nevermind",
             "never mind", "reject"}


class TurnRoute(StrEnum):
    answer = "answer"
    propose = "propose"
    confirm = "confirm"
    cancel = "cancel"
    abstain = "abstain"  # not enough signal — declined to act rather than guess
    remember = "remember"  # store a durable operator fact (memory write, no infra)


class Citation(BaseModel):
    kind: str  # event | state | incident | playbook
    ref: str
    note: str = ""


class Artifact(BaseModel):
    kind: str  # table | metric | link | text
    title: str
    data: dict[str, Any] = Field(default_factory=dict)


class TurnResult(BaseModel):
    """The structured outcome of one conversational turn — what the UI renders."""

    route: TurnRoute
    message: str
    artifacts: list[Artifact] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    intent_id: str | None = None
    confidence: float | None = None  # surfaced certainty (proposals/abstentions)
    presence: str = "speaking"


def should_abstain(confidence: float, *, floor: float) -> bool:
    """Pure: a proposed action below the confidence floor should abstain, not guess."""
    return confidence < floor


class _Decision(BaseModel):
    """The model's raw structured output. `propose` fields are required only when proposing."""

    route: str = "answer"
    message: str = ""
    intent_type: str | None = None
    target: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = None
    risk: Risk = Risk.medium
    reversible: bool = True
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    citations: list[Citation] = Field(default_factory=list)
    query: str | None = None  # the search query when route == "search" (web RAG)
    fact_key: str | None = None    # when route == "remember": the fact name (e.g. "city")
    fact_value: str | None = None  # when route == "remember": the fact value (e.g. "Brussels")
    location: str | None = None    # when route == "weather": the place (else the operator's city)
    domain: str = "general"        # "coding" → answer via the coder model + coding-expert template


def capability_summary() -> str:
    """Self-describing capability registry — answers "what can you do?" and bounds the model."""
    lines = ["You can route a request to exactly one of these capabilities (Intent types):"]
    for name in valid_intent_types() - set(ADVISORY_TYPES):
        tool = get_tool(name)
        if tool is None:
            continue
        effect = "acts on infrastructure" if tool.side_effects else "read-only"
        lines.append(f"- {name}: {effect}, rollback={tool.rollback.value}")
    lines.append("Advisory (no infrastructure change): " + ", ".join(ADVISORY_TYPES))
    return "\n".join(lines)


def _is_affirmative(text: str) -> bool:
    return text.strip().lower().rstrip(".!") in _AFFIRMATIVE


def _is_negative(text: str) -> bool:
    return text.strip().lower().rstrip(".!") in _NEGATIVE


_REMEMBER_TRIGGERS = ("remember ", "remember that ", "note that ", "keep in mind ",
                      "don't forget ", "dont forget ", "make a note ", "for the record ")
_REMIND_TRIGGERS = ("remind me ", "set a reminder ", "remind me to ")


def _looks_like_reminder(text: str) -> bool:
    """Deterministic trigger for setting a time-based reminder ('remind me to … at/in …')."""
    return text.strip().lower().startswith(_REMIND_TRIGGERS)


_PERSONAL_RE = re.compile(r"\b(i|me|my|mine|myself|i'm|i've)\b")


def _is_personal(text: str) -> bool:
    """True if the utterance is about the operator themselves (first-person).

    Used to suppress the web-search route for personal questions: those are answered from stored
    facts, and "where do I live?" must never be sent to a search engine (privacy + correctness).
    """
    return bool(_PERSONAL_RE.search(text.lower()))


def _looks_like_remember(text: str) -> bool:
    """Deterministic trigger for fact capture — an explicit imperative to remember something.

    We don't trust the weak router to classify this reliably; an explicit phrase is unambiguous,
    so we branch deterministically and only use the model for the (focused) key/value extraction.
    """
    return text.strip().lower().startswith(_REMEMBER_TRIGGERS)


_FACT_SCHEMA = {
    "type": "object",
    "properties": {"fact_key": {"type": "string"}, "fact_value": {"type": "string"}},
    "required": ["fact_key", "fact_value"],
}


_REMINDER_SCHEMA = {
    "type": "object",
    "properties": {"reminder_text": {"type": "string"}, "due_at": {"type": "string"}},
    "required": ["reminder_text", "due_at"],
}


def _extract_reminder(utterance: str) -> tuple[str, datetime] | None:
    """Focused inference: pull {reminder_text, due_at} from 'remind me …', resolved against now."""
    from jarvis.models.scheduler import Priority
    from jarvis.models.scheduler import chat as sched_chat

    now = utcnow()
    prompt = (
        f"The current time is {now.isoformat()} (UTC). Extract the reminder. Reply with ONE JSON "
        'object: {"reminder_text": <what to remind>, "due_at": <absolute ISO 8601 UTC timestamp>}. '
        'Resolve relative times against now: "in 10 minutes", "tomorrow at 9am", "tonight". '
        f"User: {utterance}"
    )
    resp = sched_chat(
        "reasoning", [{"role": "user", "content": prompt}],
        priority=Priority.INTERACTIVE, format=_REMINDER_SCHEMA,
    )
    try:
        data = json.loads(str(resp["message"]["content"]))
        text = str(data.get("reminder_text", "")).strip()
        due = datetime.fromisoformat(str(data.get("due_at", "")).replace("Z", "+00:00"))
        if due.tzinfo is None:
            due = due.replace(tzinfo=UTC)
        return (text, due) if text else None
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def _extract_fact(utterance: str) -> tuple[str, str] | None:
    """One focused inference: pull {fact_key, fact_value} from an explicit 'remember …' request."""
    from jarvis.models.scheduler import Priority
    from jarvis.models.scheduler import chat as sched_chat

    prompt = (
        "Extract the durable fact the user wants you to remember. Reply with ONE JSON object: "
        '{"fact_key": <short snake_case name>, "fact_value": <the value>}.\n'
        'Examples: "remember my city is Brussels" -> {"fact_key":"city","fact_value":"Brussels"}; '
        '"note that I prefer metric units" -> '
        '{"fact_key":"preferred_units","fact_value":"metric"}.\n'
        f"User: {utterance}"
    )
    resp = sched_chat(
        "reasoning", [{"role": "user", "content": prompt}],
        priority=Priority.INTERACTIVE, format=_FACT_SCHEMA,
    )
    try:
        data = json.loads(str(resp["message"]["content"]))
        key, value = str(data.get("fact_key", "")).strip(), str(data.get("fact_value", "")).strip()
        return (key, value) if key and value else None
    except (json.JSONDecodeError, TypeError):
        return None


def _memory_window(conn: psycopg.Connection, session: Session) -> str:
    msgs = recent_messages(conn, session.conversation_id, limit=10)
    if not msgs:
        return ""
    rendered = "\n".join(f"{m['role']}: {m['content']}" for m in msgs)
    return "Recent conversation:\n" + rendered


def _build_prompt(
    ctx_prompt: str, memory: str, utterance: str, *, search_on: bool, facts: str = ""
) -> str:
    # ANSWER is the default; only offer the search route when a search backend is actually
    # configured (otherwise a small model over-routes to a dead end).
    search_rule = (
        "- ONLY if the user explicitly asks for CURRENT EXTERNAL information (latest news, a CVE, "
        "today's weather, 'look up …', 'search the web …') OR for something that changes over time "
        "and your knowledge may be stale (newest/current/2025+ version, release date, recent "
        "events, prices), set route=\"search\" and put the query in query. NEVER search for facts "
        "about the operator themselves (where they live, their name, preferences) — those are "
        "answered from the facts below.\n"
        if search_on else ""
    )
    search_spec = ' when route="search": query (string);' if search_on else ""
    routes = (
        '"answer"|"propose"|"search"|"remember"|"weather"|"present"' if search_on
        else '"answer"|"propose"|"remember"|"weather"|"present"'
    )
    parts = [
        "You are Jarvis, an operational-intelligence assistant for a homelab. You reply with ONE "
        "JSON object and nothing else.\n"
        "ROUTING RULE (decide first; default to answer):\n"
        "- If the user asks you to DO or CHANGE infrastructure (restart/stop/start/redeploy a "
        "container, edit a file, etc.), set route=\"propose\", pick the matching intent_type "
        "from the capabilities, and fill target. Do NOT perform it — a human confirms first.\n"
        "- ONLY if the user explicitly asks you to REMEMBER a durable personal fact about them or "
        "their home (e.g. \"remember my city is Brussels\", \"note that I prefer metric units\"), "
        "set route=\"remember\" with fact_key (short, e.g. \"city\") and fact_value (e.g. "
        "\"Brussels\"). Do NOT use remember for questions or one-off chit-chat.\n"
        f"{search_rule}"
        "- If the user asks about the WEATHER or forecast — any phrasing, typos, or a follow-up "
        "like \"and for tomorrow?\" / \"this weekend?\" — set route=\"weather\". Put the place in "
        "location if they named one; leave it blank to use their saved city.\n"
        "- If the user asks to SHOW / LIST / DISPLAY / VISUALIZE their own data, OR asks a "
        "question about their own stored data — tasks, notes, documents, calendar, recipes, "
        "research, code sessions, routines, what you remember (memories/facts), torrents, and "
        "especially their MAIL/email/inbox (e.g. \"what was my last mail about the lotto?\", \"any "
        "email from the bank?\") — set route=\"present\". These come from synced data, NOT from "
        "remembered facts.\n"
        "- Otherwise — including who/what you are, your status, the homelab, explanations, and "
        "RECALLING a fact you already know about the operator (use the facts below verbatim) — set "
        "route=\"answer\" and put your grounded reply in message; cite events/state you used.\n"
        "- ALWAYS set domain: \"coding\" when the user wants HELP with programming — writing, "
        "understanding, debugging, or reviewing code, a shell/CLI command, an error/stack trace, "
        "an API, config, or a dev tool (a coding specialist answers it). Use \"general\" (NOT "
        "coding) for questions about what YOU can do, your own actions, permissions, identity or "
        "status — even if they mention containers, deploys or code. Otherwise: \"general\".\n"
        'Example — user "restart nginx" → {"route":"propose","intent_type":'
        '"docker.restart_container","target":{"container":"nginx"},"summary":"restart nginx",'
        '"message":"I can restart nginx.","risk":"medium","reversible":true,"confidence":0.9}.',
        capability_summary(),
    ]
    if facts:
        parts.append(facts)
    if memory:
        parts.append(memory)
    parts.append("Context:\n" + ctx_prompt)
    parts.append(f"User: {utterance}")
    parts.append(
        f'Output exactly one JSON object with keys: route ({routes}), '
        'message (string), and when route="propose": intent_type, target (object), summary, '
        f'risk ("low"|"medium"|"high"), reversible (bool), confidence (0..1);{search_spec} '
        ' when route="remember": fact_key (string), fact_value (string); '
        'always: domain ("general"|"coding"); '
        'Optional: citations [{kind, ref, note}]. No prose outside the JSON.'
    )
    return "\n\n".join(parts)


# Constrained-decoding schema: forces `route` to a present enum so a small model can't silently
# drop it (the failure we saw with bare format=json). Action fields stay optional.
_DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "route": {"type": "string",
                  "enum": ["answer", "propose", "search", "remember", "weather", "present"]},
        "message": {"type": "string"},
        "intent_type": {"type": "string"},
        "target": {"type": "object"},
        "summary": {"type": "string"},
        "risk": {"type": "string", "enum": ["low", "medium", "high"]},
        "reversible": {"type": "boolean"},
        "confidence": {"type": "number"},
        "query": {"type": "string"},
        "fact_key": {"type": "string"},
        "fact_value": {"type": "string"},
        "location": {"type": "string"},
        "domain": {"type": "string", "enum": ["general", "coding"]},
    },
    "required": ["route", "message"],
}


def _decide(prompt: str, *, correlation_id: str, context_ref: str) -> _Decision:
    """One inference → validated decision. Isolated so tests can monkeypatch the model."""
    from jarvis.models.scheduler import Priority
    from jarvis.models.scheduler import chat as sched_chat

    # Interactive: a human is waiting, so this preempts plan steps and background work in the queue.
    resp = sched_chat(
        "reasoning",
        [{"role": "user", "content": prompt}],
        # Route on the ACTIVE backend: when Claude is on it understands intent + follow-ups +
        # typos far better, and the same call also drafts the answer (one call, not two). Schema is
        # validated with an automatic fall-back to local, so it never goes dark.
        priority=Priority.INTERACTIVE, backend=None,
        correlation_id=correlation_id, context_ref=context_ref, format=_DECISION_SCHEMA,
    )
    raw = str(resp["message"]["content"])
    try:
        decision = _Decision.model_validate_json(raw)
        if decision.message or decision.route == "propose":
            return decision
    except ValidationError:
        pass
    # The model emitted JSON that doesn't match our schema (qwen often invents its own shape under
    # format=json). Salvage a human-readable message rather than dumping raw JSON at the user.
    return _Decision(route="answer", message=_salvage_message(raw))


def _salvage_message(raw: str) -> str:
    """Best-effort readable text from an off-schema JSON (or plain) model reply."""
    try:
        data = json.loads(raw)
    except Exception:
        return raw.strip()[:2000] or "(no response)"
    if isinstance(data, str):
        return data[:2000]
    if isinstance(data, dict):
        for key in ("message", "answer", "response", "reply", "summary", "text"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return val[:2000]
        # Fall back to a compact "key: value" rendering of scalar fields.
        parts = [f"{k}: {v}" for k, v in data.items() if isinstance(v, (str, int, float, bool))]
        if parts:
            return "\n".join(parts)[:2000]
    return raw.strip()[:2000] or "(no response)"


def respond(
    conn: psycopg.Connection, session: Session, utterance: str, *, store: Any = None
) -> TurnResult:
    """Process one user turn end-to-end: persist, reason/route, maybe propose, emit, return."""
    add_message(conn, session.conversation_id, role="user", content=utterance)

    # Deterministic fast-paths (shared with the eval via fastpath_route) short-circuit the weak
    # multi-route classifier for the unambiguous cases. A pending proposal + a yes/no still wins.
    route = fastpath_route(utterance)
    if session.pending_intent_id and _is_affirmative(utterance):
        result = _confirm(conn, session)
    elif session.pending_intent_id and _is_negative(utterance):
        result = _cancel(session)
    elif route == "reminder":
        result = _capture_reminder(conn, session, utterance, store=store)
    elif route == "remember":
        result = _capture_fact(conn, session, utterance, store=store)
    elif route == "math":
        result = _compute_answer(conn, session, utterance, store=store)
    elif route == "weather":
        result = _present_weather(conn, session, utterance, store=store)
    elif route.startswith("present"):
        # 'show my X' or a mail question — search/fetch the named source (mail searches the inbox
        # rather than falling through to the facts-only recall path).
        result = _present_data(conn, session, utterance, store=store)
    else:
        result = _reason(conn, session, utterance, store=store)

    add_message(
        conn, session.conversation_id, role="assistant", content=result.message,
        artifacts={"route": result.route.value, "intent_id": result.intent_id},
    )
    emit_event(
        Event(
            type="conversation.message", severity=Severity.info, source="conversation",
            entity_ref=f"conversation:{session.conversation_id}", occurred_at=utcnow(),
            payload={"actor": session.actor, "route": result.route.value,
                     "intent_id": result.intent_id},
            correlation_id=ids.new_id(ids.CORRELATION),
        )
    )
    return result


def _not_connected(label: str, remedy: str) -> TurnResult:
    """Accurate 'not set up yet' + remedy — instead of an empty card or a confabulated denial."""
    return TurnResult(
        route=TurnRoute.answer,
        message=f"{label} isn't connected yet — so I can't show it. To enable it: {remedy}.",
    )


def _compute_answer(
    conn: psycopg.Connection, session: Session, utterance: str, *, store: Any
) -> TurnResult:
    """Exact deterministic arithmetic (#21) — no inference. Falls back to reasoning if the
    expression can't be safely evaluated (e.g. division by zero)."""
    from jarvis.agents.calc import compute

    result = compute(utterance)
    if result is None:
        return _reason(conn, session, utterance, store=store)
    return TurnResult(route=TurnRoute.answer, message=f"= {result}")


def _looks_like_show(text: str) -> bool:
    return bool(re.search(r"\b(show|list|display|visuali[sz]e)\b", text, re.I))


_MAIL_NOUN_RE = re.compile(r"\b(e-?mails?|mails?|inbox|mailbox)\b", re.I)
_MAIL_INBOX_RE = re.compile(r"\b(inbox|mailbox)\b", re.I)
# A mail NOUN alone is too loose ("write a regex for an email address" is not a mail request);
# require a request/ownership cue too — unless it's literally the inbox.
_MAIL_CONTEXT_RE = re.compile(
    r"\b(my|me|unread|from|about|new|reply|replied|sender|sent|received|read|check|any|latest|"
    r"last|recent|spam|junk|forward|subject)\b", re.I
)
_MAIL_ABOUT_RE = re.compile(
    r"\b(?:about|regarding|re|concerning|on the (?:subject|topic) of)\b[:\s]+(.+?)[?.!]*$", re.I
)
_MAIL_FROM_RE = re.compile(r"\bfrom\s+(.+?)[?.!]*$", re.I)
_MAIL_STOPWORDS = {"the", "my", "a", "an", "any", "some", "that", "this"}


def _looks_like_mail(text: str) -> bool:
    """A mail question/request — distinct from merely mentioning 'email' in a coding/knowledge
    question. Fires on the inbox outright, else needs a mail noun PLUS a request/ownership cue.
    Reminders/remember are matched earlier in respond(), so 'remind me to email X' never reaches."""
    if not _MAIL_NOUN_RE.search(text):
        return False
    if _MAIL_INBOX_RE.search(text):
        return True
    return bool(_MAIL_CONTEXT_RE.search(text))


def _mail_topic(text: str) -> str:
    """Pull the search topic from 'mail about <X>' / 'email from <Y>'; '' → show recent inbox."""
    m = _MAIL_ABOUT_RE.search(text) or _MAIL_FROM_RE.search(text)
    if not m:
        return ""
    words = m.group(1).strip().split()
    while words and words[0].lower() in _MAIL_STOPWORDS:
        words.pop(0)
    return " ".join(words)


def _present_mail(
    conn: psycopg.Connection, session: Session, utterance: str, *, store: Any
) -> TurnResult:
    """Answer mail questions from the synced inbox: keyword-search on a topic, else the latest.
    Gives an accurate 'no such mail' when the inbox has nothing — never falls back to stored facts.
    """
    if not capabilities.available("email"):
        return _not_connected("Email", capabilities.remedy("email"))
    from jarvis.mail import repository as r

    topic = _mail_topic(utterance)
    msgs = r.find(conn, topic, limit=10) if topic else r.recent(conn, limit=20)
    if not msgs:
        where = f' about “{topic}”' if topic else ""
        return TurnResult(
            route=TurnRoute.answer,
            message=f"I don't see any mail{where} in your synced inbox.",
        )
    rows = [{"from": m.from_addr, "subject": m.subject,
             "date": m.received_at.strftime("%d %b %H:%M") if m.received_at else "",
             "importance": m.triage.importance.value if m.triage else "-"} for m in msgs]
    wants_one = bool(topic) or re.search(r"\b(last|latest|recent|most recent)\b", utterance, re.I)
    if wants_one:
        top = msgs[0]
        when = f" ({top.received_at.strftime('%d %b')})" if top.received_at else ""
        about = f' about “{topic}”' if topic else ""
        message = f"Your latest mail{about} — from {top.from_addr}, “{top.subject}”{when}."
        snippet = (top.triage.summary if top.triage and top.triage.summary else top.snippet)
        if snippet:
            message += f" {snippet[:220].strip()}"
        title = f"Mail · {topic}" if topic else "Latest mail"
        return TurnResult(route=TurnRoute.answer, message=message,
                          artifacts=[auto_artifact(title, rows)])
    return TurnResult(route=TurnRoute.answer, message="Here's your inbox:",
                      artifacts=[auto_artifact("Inbox", rows)])


# Ordered (key, pattern); first match wins. The single source of truth for "which workspace panel
# does this utterance name?" — shared by _present_data (what to fetch) and fastpath_route (the eval
# + dispatch label), so the two can never drift apart (the class of bug behind the mail regression).
_PRESENT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (key, re.compile(pat, re.I)) for key, pat in (
        ("hots", r"\b(hots|heroes of the storm|patch notes|overlay)\b"),
        ("orpheus", r"\borpheus\b"),
        ("world_news", r"\bworld news\b"),
        ("tasks", r"\btask"),
        ("notes", r"\bnote"),
        ("mail", r"\b(mail|inbox|email)"),
        ("calendar", r"\b(calendar|agenda|schedule|event)"),
        ("recipes", r"\brecipe"),
        ("research", r"\bresearch"),
        ("documents", r"\b(documents?|docs?|reports?)\b"),
        ("code", r"\b(code|diff|patch|coding)\b"),
        ("routines", r"\b(routine|automation|scheduled)"),
        ("memories", r"\b(memor|fact|what you know|what you remember)"),
        ("torrents", r"\b(torrent|download)"),
    )
)


def _present_target(text: str) -> str | None:
    """The workspace data source this utterance names, else None (nothing presentable)."""
    for key, pat in _PRESENT_PATTERNS:
        if pat.search(text):
            return key
    return None


def fastpath_route(utterance: str) -> str:
    """The deterministic handler respond() selects from utterance content alone (ignoring pending
    confirmations). Returns a stable label — 'reminder' | 'remember' | 'weather' | 'present:<src>' |
    'llm' (nothing matched → the LLM router decides). Single source of truth shared by respond() and
    the behavioral eval suite, so a routing regression shows up as a failing eval case."""
    if _looks_like_reminder(utterance):
        return "reminder"
    if _looks_like_remember(utterance):
        return "remember"
    if looks_like_weather(utterance):
        return "weather"
    # A show-verb only routes to a presenter when it actually names a known data source — otherwise
    # the noun "list" ("difference between a list and a tuple") would hijack a coding question.
    if _looks_like_show(utterance):
        target = _present_target(utterance)
        if target:
            return f"present:{target}"
    if _looks_like_mail(utterance):
        return "present:mail"
    # Named homelab apps (HotS, Orpheus) are specific enough to present on mention alone — no
    # show-verb needed ("what's the latest hots patch?"). Other targets still require a show-verb.
    app = _present_target(utterance)
    if app in ("hots", "orpheus", "world_news"):
        return f"present:{app}"
    # A pure arithmetic ask → exact deterministic compute (no inference). Strict detector, so word
    # problems and code questions still fall through to the model.
    from jarvis.agents.calc import looks_like_math
    if looks_like_math(utterance):
        return "math"
    return "llm"


def _present_hots(utterance: str) -> TurnResult:
    """Present Heroes of the Storm data: the OVERLAY app's recent matches when asked about
    matches/games/overlay, else the patch-notes app's latest patches (default) or hero roster.
    Accurate 'not reachable'/'no data yet' messaging — never a confabulated denial."""
    if re.search(r"\b(overlay|match|game|replay)", utterance, re.I):
        from jarvis.connectors import hots_overlay
        if not hots_overlay.reachable():
            return _not_connected("HotS Overlay", capabilities.remedy("hots overlay"))
        matches = hots_overlay.recent_matches(10)
        if not matches:
            return TurnResult(
                route=TurnRoute.answer,
                message="No HotS matches recorded yet — run the replay uploader on your gaming PC.",
            )
        return TurnResult(route=TurnRoute.answer, message="Your recent HotS matches:",
                          artifacts=[auto_artifact("HotS Matches", matches)])

    from jarvis.connectors import hots

    if not hots.reachable():
        return _not_connected("Heroes of the Storm", capabilities.remedy("heroes of the storm"))
    if re.search(r"\bhero", utterance, re.I):
        return TurnResult(route=TurnRoute.answer, message="Here's the HotS hero roster:",
                          artifacts=[auto_artifact("HotS Heroes", hots.heroes())])
    return TurnResult(route=TurnRoute.answer, message="Here are the latest HotS patches:",
                      artifacts=[auto_artifact("HotS Patches", hots.latest_patches(10))])


def _present_world_news() -> TurnResult:
    """Report the World News service status. The app is a skeleton (no articles yet), so this
    surfaces reachability + the gateway's stub greeting — a placeholder for real news later."""
    from jarvis.connectors import world_news

    if not world_news.reachable():
        return _not_connected("World News", capabilities.remedy("world news"))
    return TurnResult(
        route=TurnRoute.answer,
        message=f"World News is up — but it's still a skeleton with no articles yet. "
                f"The gateway says: \"{world_news.hello()}\".",
    )


def _present_orpheus(utterance: str) -> TurnResult:
    """Present Orpheus state: what's playing (default) or the active session. Distinguishes down
    (not reachable) from dormant (running, Spotify not connected) so the message is accurate."""
    from jarvis.connectors import orpheus

    if not orpheus.reachable():
        return _not_connected("Orpheus", capabilities.remedy("orpheus"))
    if not orpheus.authed():
        return TurnResult(
            route=TurnRoute.answer,
            message="Orpheus is running, but Spotify isn't connected yet — add your Spotify "
                    "credentials (SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET) to enable playback.",
        )
    if re.search(r"\bsession", utterance, re.I):
        return TurnResult(route=TurnRoute.answer, message="Orpheus session:",
                          artifacts=[auto_artifact("Orpheus — Session", orpheus.active_session())])
    np = orpheus.now_playing()
    if not np.get("current") or not np.get("isPlaying"):
        return TurnResult(route=TurnRoute.answer,
                          message="Orpheus isn't playing anything right now.")
    return TurnResult(route=TurnRoute.answer, message="Now playing on Orpheus:",
                      artifacts=[auto_artifact("Orpheus — Now Playing", np)])


def _present_data(
    conn: psycopg.Connection, session: Session, utterance: str, *, store: Any
) -> TurnResult:
    """Generic 'show me my <X>' → fetch X's data → a universal artifact the app renders as cards.
    Known modules get clean projections; unknown shapes still render via the auto renderer. Falls
    back to normal reasoning when the request names nothing presentable."""
    target = _present_target(utterance)
    if target == "mail":
        return _present_mail(conn, session, utterance, store=store)
    if target == "hots":
        return _present_hots(utterance)
    if target == "orpheus":
        return _present_orpheus(utterance)
    if target == "world_news":
        return _present_world_news()
    title: str | None = None
    data: Any = None
    if target == "tasks":
        from jarvis.tasks import repository as r
        title = "Open tasks"
        data = [{"title": x.title, "status": x.status.value, "priority": x.priority.value,
                 "due": x.due_at.isoformat()[:16].replace("T", " ") if x.due_at else ""}
                for x in r.list_open(conn)]
    elif target == "notes":
        from jarvis.notes import repository as r
        title = "Notes"
        data = [{"title": x.title, "tags": ", ".join(x.tags)} for x in r.recent(conn)]
    elif target == "calendar":
        if not capabilities.available("calendar"):
            return _not_connected("Calendar", capabilities.remedy("calendar"))
        from jarvis.calendar import repository as r
        evs = r.agenda(conn, utcnow(), utcnow() + timedelta(days=30))
        title = "Agenda"
        data = [{"when": e.starts_at.isoformat()[:16].replace("T", " "), "title": e.title,
                 "source": e.source.value} for e in evs]
    elif target == "recipes":
        from jarvis.recipes import repository as r
        title = "Recipes"
        data = [{"title": x.title, "servings": x.servings or "", "tags": ", ".join(x.tags)}
                for x in r.recent(conn)]
    elif target == "research":
        from jarvis.research import repository as r
        title = "Research"
        data = [{"query": x.query, "status": x.status.value} for x in r.recent(conn, limit=10)]
    elif target == "documents":
        from jarvis.documents import repository as r
        title = "Documents"
        data = [{"title": x.title, "status": x.status.value,
                 "updated": x.updated_at.isoformat()[:10]} for x in r.recent(conn)]
    elif target == "code":
        if not capabilities.available("code"):
            return _not_connected("Code", capabilities.remedy("code"))
        from jarvis.code import repository as r
        title = "Code sessions"
        data = [{"task": x.task, "repo": x.repo_path.rsplit("/", 1)[-1], "status": x.status.value,
                 "files": len(x.files_changed), "applied": x.applied} for x in r.recent(conn)]
    elif target == "routines":
        from jarvis.routines.repository import list_routines
        title = "Routines"
        data = [{"name": x.name, "action": x.action.kind.value, "schedule": x.schedule.kind.value,
                 "enabled": x.enabled,
                 "last_run": x.last_run.isoformat()[:16].replace("T", " ") if x.last_run else "—"}
                for x in list_routines(conn)]
    elif target == "memories":
        title = "What I remember"
        data = [{"about": f.key.replace("_", " "), "value": f.value} for f in list_facts(conn)]
    elif target == "torrents":
        try:
            from jarvis.connectors.qbittorrent import fetch_snapshot
            title, data = "Torrents", fetch_snapshot()  # raw shape → universal renderer handles it
        except Exception:  # noqa: BLE001 — connector off/unreachable → fall back
            data = None
    if not data:
        return _reason(conn, session, utterance, store=store)
    return TurnResult(route=TurnRoute.answer, message=f"Here's your {title.lower()}:",
                      artifacts=[auto_artifact(title, data)])


def _operator_city(conn: psycopg.Connection) -> str | None:
    """Fall back to the operator's stored city fact when a weather request names no place."""
    for f in list_facts(conn):
        if f.key in ("city", "location", "hometown"):
            return f.value
    return None


def _present_weather(
    conn: psycopg.Connection, session: Session, utterance: str, *, store: Any,
    location: str | None = None,
) -> TurnResult:
    """Deterministic weather presenter: resolve a place → fetch open-meteo → a `weather` artifact
    the app renders as a card. Falls back to reasoning/search if no place resolves or fetch dies."""
    location = location or extract_location(utterance) or _operator_city(conn)
    if not location:
        # No city in the question and none on file — ask, rather than fall through to a generic
        # answer (which on Claude wrongly claims there's no weather integration).
        return TurnResult(
            route=TurnRoute.answer,
            message="Which city's weather? Tip: say \"remember my city is Brussels\" and I'll "
                    "use it by default.",
        )
    try:
        view = weather_view(location)
    except WeatherUnavailable:
        # I HAVE weather — the service is just briefly down/rate-limited. Say so accurately +
        # offer the remedy, instead of falsely claiming "no access".
        return TurnResult(
            route=TurnRoute.answer,
            message=f"I can pull the weather for {location}, but the weather service didn't "
                    "respond just now (it briefly rate-limited me). Ask again in a minute.",
        )
    if view is None:  # the place genuinely couldn't be found
        return TurnResult(
            route=TurnRoute.answer,
            message=f"I couldn't find “{location}” on the map — try a nearby town or city?",
        )
    cur = view["data"]["current"]
    temp = f"{cur['temp']}°C" if cur["temp"] is not None else "—"
    message = f"{view['data']['location']}: {temp}, {cur['label'].lower()}."
    return TurnResult(
        route=TurnRoute.answer, message=message,
        artifacts=[Artifact(kind="weather", title=view["title"], data=view["data"])],
    )


def _reason(
    conn: psycopg.Connection, session: Session, utterance: str, *, store: Any
) -> TurnResult:
    # Answer cache (#22): a repeated self-contained coding question short-circuits the WHOLE
    # pipeline — no routing inference, no specialist call, no sandbox. Only coding answers are ever
    # stored, so a hit is necessarily a prior vetted coding answer.
    from jarvis.agents import answer_cache
    cached = answer_cache.get(utterance)
    if cached is not None:
        return TurnResult(route=TurnRoute.answer, message=cached)

    since = utcnow() - timedelta(hours=_WINDOW_HOURS)
    ctx = assemble_context(conn, since=since, query=utterance, store=store)
    search_on = bool(get_settings().searxng_url)
    facts = facts_block(conn)  # durable operator facts → always recalled in context
    prompt = _build_prompt(
        ctx.prompt, _memory_window(conn, session), utterance, search_on=search_on, facts=facts
    )
    decision = _decide(
        prompt, correlation_id=ids.new_id(ids.CORRELATION), context_ref=ctx.context_ref
    )

    # Remember route: store a durable fact (a memory write — safe, no infra gate). Needs both
    # key and value; otherwise fall through to a normal answer.
    if decision.route == "remember" and decision.fact_key and decision.fact_value:
        return _remember(conn, decision.fact_key, decision.fact_value)

    # Presenter routes (the smart path, for what the deterministic fast-paths in respond() missed —
    # follow-ups, typos, paraphrases): the model recognized a weather ask or a "show my X" request.
    if decision.route == "weather":
        return _present_weather(conn, session, utterance, store=store, location=decision.location)
    if decision.route == "present":
        return _present_data(conn, session, utterance, store=store)

    # Only honor a search route when a backend exists AND the question isn't personal — the
    # operator's own info comes from facts, never a web search. Otherwise fall through to answer.
    if (
        decision.route == "search" and search_on
        and not _is_personal(utterance) and (decision.query or utterance)
    ):
        return _search_answer(decision.query or utterance)

    if decision.route == "propose" and decision.intent_type in valid_intent_types():
        floor = get_settings().abstain_confidence_floor
        if should_abstain(decision.confidence, floor=floor):
            # Not enough signal to act — say so instead of proposing a low-confidence action.
            pct = round(decision.confidence * 100)
            return TurnResult(
                route=TurnRoute.abstain, confidence=decision.confidence,
                message=(
                    f"I'm not confident enough ({pct}%) to act on that yet. "
                    "I'd want more signal first — ask me to investigate, or confirm the target."
                ),
            )
        intent = _make_intent(decision, ctx.context_ref, session.actor)
        insert_intent(conn, intent)
        session.pending_intent_id = intent.intent_id
        tool = get_tool(intent.type)
        verb = "act on infrastructure" if (tool and tool.side_effects) else "run"
        msg = decision.message or f"I can {verb} via `{intent.type}`."
        msg += " Confirm to proceed (reply 'yes'), or 'no' to cancel."
        return TurnResult(
            route=TurnRoute.propose, message=msg, intent_id=intent.intent_id,
            citations=decision.citations, confidence=decision.confidence,
        )

    # Coding/technical question → a coding-specialist pass (coder model locally, Claude when on)
    # under a coding-expert template grounded in the operator's real environment. Runs before
    # personal-recall so "why am I getting this error?" isn't mistaken for a stored-fact lookup.
    if decision.route == "answer" and decision.domain == "coding":
        return _code_answer(ctx.prompt, _memory_window(conn, session), utterance, facts=facts)

    # Personal question + we have facts → answer from them with a FOCUSED, grounded inference.
    # The big multi-route prompt drowns the fact for a small model (it confabulated "New York");
    # a tight facts-only prompt recalls reliably. Runs after propose/search so those still win.
    if facts and _is_personal(utterance):
        return TurnResult(route=TurnRoute.answer, message=_recall_answer(facts, utterance))

    # Answer route. The routing call ran on the ACTIVE backend (Claude when on), so `message` is
    # already that backend's answer — use it directly (one call, not two). Only re-compose if the
    # model returned an empty message (the "(no response)" guard).
    message = decision.message.strip() or _plain_answer(
        ctx.prompt, _memory_window(conn, session), utterance, facts=facts
    )
    # Escalation ladder (#2): if the local backend produced nothing usable, retry once on the
    # stronger backend so Jarvis never goes silent. No-op when already on Claude.
    if _should_escalate(message):
        escalated = _plain_answer(
            ctx.prompt, _memory_window(conn, session), utterance, facts=facts, backend="claude"
        )
        if escalated and escalated != "(no response)":
            message = escalated
    return TurnResult(
        route=TurnRoute.answer, message=message, citations=decision.citations,
    )


def _ask_coder(prompt: str) -> str:
    """One coding-specialist inference (coder model locally / Claude when active)."""
    from jarvis.models.scheduler import Priority
    from jarvis.models.scheduler import chat as sched_chat

    resp = sched_chat("coder", [{"role": "user", "content": prompt}], priority=Priority.INTERACTIVE)
    return str(resp["message"]["content"]).strip() or "(no response)"


def _code_answer(ctx_prompt: str, memory: str, utterance: str, *, facts: str = "") -> TurnResult:
    """Answer a coding/technical question with the CODER model (local) or Claude (when active),
    under a coding-expert template grounded in the operator's real environment (#6). The generated
    code is syntax-checked (ast.parse / json.loads, no execution); on a syntax error we re-ask ONCE
    with the error fed back (#24). role='coder' selects qwen2.5-coder locally; ignored on Claude."""
    from jarvis.agents import answer_cache
    from jarvis.agents.code_validation import syntax_issues
    from jarvis.agents.environment import environment_block

    cached = answer_cache.get(utterance)
    if cached is not None:
        return TurnResult(route=TurnRoute.answer, message=cached)

    prompt = (
        "You are a senior software engineer. Answer the coding question precisely and correctly. "
        "Prefer working, runnable code; state assumptions; be concise. If you write code, give a "
        "one-line plan first, then the code, then note edge cases or version caveats. If you are "
        "not confident an approach is correct, say what you're unsure about rather than guessing. "
        "Target the operator's exact environment below.\n\n"
        + environment_block() + "\n\n"
        + (facts + "\n\n" if facts else "")
        + (memory + "\n\n" if memory else "")
        + ("Context:\n" + ctx_prompt + "\n\n" if ctx_prompt.strip() else "")
        + f"Question: {utterance}"
    )
    message = _ask_coder(prompt)
    issues = syntax_issues(message)
    if issues:
        # The code didn't parse — give the model the exact error and one chance to fix it. Pure
        # syntax check (no execution), so this is safe and bounds the turn to two inferences.
        retry = (
            prompt + "\n\nYour previous answer had syntax errors:\n- " + "\n- ".join(issues)
            + "\n\nPrevious answer:\n" + message
            + "\n\nReturn a corrected answer — the code MUST parse."
        )
        message = _ask_coder(retry)
    else:
        # Syntax is fine → optionally RUN it in the sandbox (Wave 1.2, opt-in) and, on a real
        # runtime failure, re-ask once with the actual traceback. No-op unless code_exec_enabled.
        from jarvis.agents.code_sandbox import verify
        failure = verify(message)
        if failure:
            retry = (
                prompt + f"\n\nWhen I ran your code in a sandbox it failed:\n{failure}\n\n"
                "Previous answer:\n" + message
                + "\n\nReturn a corrected answer that runs cleanly, or explain why the snippet is "
                "illustrative and isn't meant to run standalone."
            )
            message = _ask_coder(retry)
    # Cache the vetted answer (no-op for context-dependent / short questions) so an identical
    # repeat skips the coder + verification entirely.
    answer_cache.put(utterance, message)
    return TurnResult(route=TurnRoute.answer, message=message)


def _recall_answer(facts: str, utterance: str) -> str:
    """Focused, strictly-grounded recall — answer ONLY from stored facts (small-model reliable)."""
    from jarvis.models.scheduler import Priority
    from jarvis.models.scheduler import chat as sched_chat

    prompt = (
        "Answer the question using ONLY these stored facts about the operator. Quote the relevant "
        "value. If the facts don't contain the answer, say you don't have it noted yet — do not "
        "invent.\n\n" + facts + f"\n\nQuestion: {utterance}\nAnswer in one short sentence."
    )
    resp = sched_chat(
        "reasoning", [{"role": "user", "content": prompt}], priority=Priority.INTERACTIVE
    )
    return str(resp["message"]["content"]).strip() or "(no response)"


def _remember(conn: psycopg.Connection, key: str, value: str) -> TurnResult:
    """Persist a durable operator fact, then confirm. Validation lives in the facts model."""
    try:
        fact = set_fact(conn, key, value)
    except ValueError as exc:  # malformed key/value from the model → don't store, just answer
        return TurnResult(route=TurnRoute.answer, message=f"I couldn't note that: {exc}")
    return TurnResult(
        route=TurnRoute.remember,
        message=f"Got it — I'll remember that {fact.key.replace('_', ' ')} is {fact.value}.",
    )


def _capture_fact(
    conn: psycopg.Connection, session: Session, utterance: str, *, store: Any
) -> TurnResult:
    """Deterministic 'remember …' path: focused extraction → store. Falls back to normal
    reasoning if no clean key/value can be pulled (so a misfire never dead-ends the turn)."""
    extracted = _extract_fact(utterance)
    if extracted is None:
        return _reason(conn, session, utterance, store=store)
    return _remember(conn, *extracted)


def _capture_reminder(
    conn: psycopg.Connection, session: Session, utterance: str, *, store: Any
) -> TurnResult:
    """Deterministic 'remind me …' path: focused extraction → schedule. Falls back to reasoning
    if no clean text/time can be pulled."""
    from jarvis.reminders import add_reminder

    extracted = _extract_reminder(utterance)
    if extracted is None:
        return _reason(conn, session, utterance, store=store)
    text, due = extracted
    try:
        rem = add_reminder(conn, text, due)
    except ValueError:
        return _reason(conn, session, utterance, store=store)
    when = rem.due_at.strftime("%a %d %b %H:%M UTC")
    return TurnResult(route=TurnRoute.remember, message=f"Reminder set: \"{rem.text}\" — {when}.")




def _plain_answer(
    ctx_prompt: str, memory: str, utterance: str, *, facts: str = "", backend: str | None = None
) -> str:
    """A plain grounded answer — fallback when structured routing yields no message. `backend` pins
    the brain (used by the escalation ladder to retry on Claude); None → the active backend."""
    from jarvis.models.scheduler import Priority
    from jarvis.models.scheduler import chat as sched_chat

    prompt = (
        "Answer the user concisely and grounded in the context below; if it's about you, use your "
        "identity. Cite events/state you rely on.\n\n"
        + (facts + "\n\n" if facts else "")
        + (memory + "\n\n" if memory else "")
        + "Context:\n" + ctx_prompt + f"\n\nUser: {utterance}"
    )
    resp = sched_chat(
        "reasoning", [{"role": "user", "content": prompt}],
        priority=Priority.INTERACTIVE, backend=backend,
    )
    return str(resp["message"]["content"]).strip() or "(no response)"


def _should_escalate(message: str) -> bool:
    """The escalation ladder (#2): a LOCAL backend that produced nothing usable → retry once on the
    stronger backend so Jarvis never goes silent. Conservative — fires only on an empty/non-answer,
    and only when the active backend is local (no-op when already on Claude)."""
    from jarvis.models.backends.state import cached_default_backend

    if cached_default_backend() != "local":
        return False
    return (not message) or message == "(no response)" or len(message.strip()) < 2


def _search_answer(query: str) -> TurnResult:
    """Web RAG: retrieve results, synthesize a cited answer, render the sources as an artifact."""
    from jarvis.search.rag import answer_with_search

    try:
        message, results = answer_with_search(query)
    except Exception as exc:  # noqa: BLE001 — search/egress failure degrades to a plain note
        return TurnResult(route=TurnRoute.answer, message=f"Search is unavailable: {exc}")
    citations = [Citation(kind="web", ref=r.url, note=r.title) for r in results]
    sources = Artifact(
        kind="table", title="Sources",
        data={"columns": ["#", "title", "url"],
              "rows": [[i + 1, r.title, r.url] for i, r in enumerate(results)]},
    )
    return TurnResult(
        route=TurnRoute.answer, message=message, citations=citations, artifacts=[sources],
    )


def _make_intent(decision: _Decision, context_ref: str, actor: str) -> Intent:
    tool = get_tool(decision.intent_type or "")
    requires_approval = (tool.side_effects if tool else False) or decision.risk is Risk.high
    return Intent(
        type=decision.intent_type or "",
        target=decision.target,
        reasoning=IntentReasoning(
            summary=decision.summary or decision.message or decision.intent_type or "",
            confidence=decision.confidence, risk=decision.risk, reversible=decision.reversible,
        ),
        requested_by=f"user:{actor}",
        context_ref=context_ref,
        requires_approval=requires_approval,
        correlation_id=ids.new_id(ids.CORRELATION),
    )


def _confirm(conn: psycopg.Connection, session: Session) -> TurnResult:
    from jarvis.audit.log import record
    from jarvis.intents import service

    intent_id = session.pending_intent_id
    session.pending_intent_id = None
    try:
        service.approve(conn, intent_id)
        record(conn, actor=f"user:{session.actor}", action="intent.approve", target=intent_id)
        execution = service.execute(conn, intent_id)
        record(conn, actor=f"user:{session.actor}", action="intent.execute",
               target=intent_id, outcome=execution.outcome.value)
        return TurnResult(
            route=TurnRoute.confirm,
            message=f"Done — executed `{intent_id}` → {execution.outcome.value}.",
            intent_id=intent_id,
        )
    except service.ModeBlocked as exc:
        return TurnResult(route=TurnRoute.confirm,
                          message=f"Blocked by operational mode: {exc}", intent_id=intent_id)
    except service.ApprovalRequired as exc:
        return TurnResult(
            route=TurnRoute.confirm,
            message=f"Approved, but execution still gated: {exc}", intent_id=intent_id,
        )


def _cancel(session: Session) -> TurnResult:
    intent_id = session.pending_intent_id
    session.pending_intent_id = None
    return TurnResult(route=TurnRoute.cancel, message="Cancelled — nothing was run.",
                      intent_id=intent_id)
