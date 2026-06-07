"""Capability status registry — what Jarvis can actually do *right now*, config-driven.

One source of truth so Jarvis (a) tells the operator accurately what it can do, (b) only says "I
can't / no access" for things that are genuinely not connected, and (c) offers the remedy to enable
them. The persona reads this into its prompt; the presenter reads it to give a remedy instead of an
empty card or a confabulated denial. Pure config/secret checks — cheap, no DB, safe every turn.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Capability:
    name: str
    available: bool
    does: str       # what it does, for the "what I can do now" line
    remedy: str     # how to switch it on, when it isn't


def status() -> list[Capability]:
    from jarvis.config import get_settings
    from jarvis.security.secrets import get_provider

    s = get_settings()
    sec = get_provider()
    search_on = bool(s.searxng_url)
    mail_on = bool(s.imap_host or s.mail_accounts)
    cal_on = bool(sec.get("GOOGLE_OAUTH_REFRESH_TOKEN")) or bool(s.calendar_ics_urls)
    code_on = bool(s.code_repo_allowlist)
    code_exec_on = bool(s.code_exec_enabled)
    hots_on = bool(s.hots_api_url)
    hots_overlay_on = bool(s.hots_overlay_url)
    orpheus_on = bool(s.orpheus_api_url)
    world_news_on = bool(s.news_enabled)
    return [
        Capability("weather", True, "show the live weather and 5-day forecast for any city", ""),
        Capability("tasks", True, "create, list and complete the operator's tasks", ""),
        Capability("notes", True, "capture and recall markdown notes", ""),
        Capability("recipes", True, "store recipes and import them from a URL", ""),
        Capability("documents", True, "draft and revise markdown documents", ""),
        Capability("memory", True, "remember and recall durable facts about the operator", ""),
        Capability("routines", True, "run and manage scheduled routines (briefings, checks)", ""),
        Capability("web search", search_on, "search the web for current info, with citations",
                   "set SEARXNG_URL"),
        Capability("deep research", search_on, "run multi-source web research into a report",
                   "enable web search (SEARXNG_URL)"),
        Capability("email", mail_on, "read, triage and draft replies to the inbox",
                   "add IMAP host + an app-password (IMAP_HOST, MAIL_USERNAME, MAIL_PASSWORD)"),
        Capability("calendar", cal_on, "show the agenda and add events",
                   "connect Google Calendar (run `make google-oauth`) or add an ICS URL"),
        Capability("code", code_on, "run sandboxed coding sessions on allowlisted repos",
                   "set CODE_REPO_ALLOWLIST (and install OpenCode on the box)"),
        Capability("code execution", code_exec_on,
                   "run generated code in a throwaway sandbox to verify it actually works",
                   "set CODE_EXEC_ENABLED=true (Docker required on the box)"),
        Capability("heroes of the storm", hots_on,
                   "show Heroes of the Storm patch notes and the hero roster",
                   "deploy the HotS app on the box and set HOTS_API_URL"),
        Capability("hots overlay", hots_overlay_on,
                   "show recent Heroes of the Storm matches from the streaming overlay",
                   "deploy the HotS Overlay app on the box and set HOTS_OVERLAY_URL"),
        Capability("orpheus", orpheus_on,
                   "show what the Orpheus music system is playing and its session",
                   "deploy the Orpheus app on the box and set ORPHEUS_API_URL"),
        Capability("world news", world_news_on,
                   "show pooled, AI-summarized world news and search it by topic",
                   "migrate the news schema on the box and set NEWS_ENABLED=true"),
        Capability("gpu", True,
                   "report GPU/VRAM occupancy — which models are resident, their VRAM, and when "
                   "Ollama frees them — and unload them on request ('free the GPU')", ""),
    ]


def available(name: str) -> bool:
    return any(c.name == name and c.available for c in status())


def remedy(name: str) -> str:
    return next((c.remedy for c in status() if c.name == name), "")
