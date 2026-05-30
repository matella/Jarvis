"""Scheduled routines (cross-cutting track A) — proactive briefings over existing capabilities.

A routine is a schedule + an action that composes things the system already does (summarize,
search, query incidents) — no new reasoning path. The daemon fires due routines (change-aware via
last_run; suspended under maintenance) and emits a `routine.completed` event + optional
notification. This is what turns Jarvis from reactive into a personal operational assistant.
"""
