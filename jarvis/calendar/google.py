"""Google Calendar read-mirror sync — OAuth refresh → list events → upsert mirror rows.

v1 is READ-ONLY (no write-back). The parse (`to_event`) + `sync` (with an injected `fetch_fn`) are
unit-tested; `_default_fetch` (real OAuth refresh + events.list over guarded egress) needs the
`make google-oauth` refresh token (ON HOLD until the operator mints it). Mirror events are deduped
by their Google event id (`external_uid`).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from jarvis.calendar.models import CalendarEvent, EventSource, EventStatus
from jarvis.db import connect

FetchFn = Callable[[int], list[dict]]  # horizon_days -> list of Google event resources


def _parse_dt(node: dict | None) -> tuple[datetime | None, bool]:
    """Google start/end is {dateTime} (timed) or {date} (all-day). Returns (dt, all_day)."""
    if not node:
        return None, False
    if "dateTime" in node:
        return datetime.fromisoformat(node["dateTime"]), False
    if "date" in node:
        return datetime.fromisoformat(node["date"]), True
    return None, False


def to_event(item: dict[str, Any]) -> CalendarEvent | None:
    """Map one Google Calendar event resource → a mirror CalendarEvent (None if unusable)."""
    uid = item.get("id")
    if not uid or item.get("status") == "cancelled":
        return None
    starts_at, all_day = _parse_dt(item.get("start"))
    if starts_at is None:
        return None
    ends_at, _ = _parse_dt(item.get("end"))
    status = EventStatus.tentative if item.get("status") == "tentative" else EventStatus.confirmed
    return CalendarEvent(
        source=EventSource.google,
        external_uid=str(uid),
        title=str(item.get("summary") or "(no title)"),
        location=str(item.get("location") or ""),
        description=str(item.get("description") or ""),
        starts_at=starts_at,
        ends_at=ends_at,
        all_day=all_day,
        rrule=(item.get("recurrence") or [None])[0],
        status=status,
    )


def sync(*, fetch_fn: FetchFn | None = None, horizon_days: int = 30, conn_factory=connect) -> int:
    """Pull Google events within the horizon and upsert them as mirror rows. Returns count."""
    from jarvis.calendar import repository

    fetch_fn = fetch_fn or _default_fetch
    items = fetch_fn(horizon_days)
    synced = 0
    with conn_factory() as conn:
        for item in items:
            event = to_event(item)
            if event is not None:
                repository.upsert_mirror(conn, event)
                synced += 1
    return synced


def _default_fetch(horizon_days: int) -> list[dict]:  # pragma: no cover — needs live OAuth (held)
    """Real fetch: refresh the access token, list primary-calendar events over guarded egress.

    ON HOLD until `make google-oauth` mints GOOGLE_OAUTH_REFRESH_TOKEN into the box .env.
    """
    import json
    import urllib.parse
    from datetime import timedelta

    from jarvis.events.models import utcnow
    from jarvis.security.egress import guarded_request
    from jarvis.security.secrets import get_provider

    s = get_provider()
    token_body = urllib.parse.urlencode({
        "client_id": s.required("GOOGLE_OAUTH_CLIENT_ID"),
        "client_secret": s.required("GOOGLE_OAUTH_CLIENT_SECRET"),
        "refresh_token": s.required("GOOGLE_OAUTH_REFRESH_TOKEN"),
        "grant_type": "refresh_token",
    }).encode()
    with guarded_request("https://oauth2.googleapis.com/token", data=token_body) as resp:
        access = json.loads(resp.read())["access_token"]
    now = utcnow()
    params = urllib.parse.urlencode({
        "timeMin": now.isoformat(), "timeMax": (now + timedelta(days=horizon_days)).isoformat(),
        "singleEvents": "true", "orderBy": "startTime", "maxResults": "250",
    })
    url = f"https://www.googleapis.com/calendar/v3/calendars/primary/events?{params}"
    with guarded_request(url, headers={"Authorization": f"Bearer {access}"}) as resp:
        return json.loads(resp.read()).get("items", [])
