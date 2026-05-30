"""Calendar ICS parsing + HA state-change detection — pure unit (no I/O)."""

from __future__ import annotations

from datetime import UTC, datetime

from jarvis.connectors import homeassistant as ha
from jarvis.connectors.calendar import parse_ics

ICS = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:evt-1@cal
SUMMARY:Dentist appointment
DTSTART:20260531T090000Z
END:VEVENT
BEGIN:VEVENT
UID:evt-2@cal
SUMMARY:Long title that is folded
 across two lines
DTSTART;TZID=Europe/Brussels:20260601T180000
END:VEVENT
END:VCALENDAR"""


def test_parse_ics_extracts_events_and_unfolds() -> None:
    events = parse_ics(ICS)
    assert len(events) == 2
    assert events[0].uid == "evt-1@cal" and events[0].summary == "Dentist appointment"
    assert events[0].start == datetime(2026, 5, 31, 9, 0, tzinfo=UTC)
    # RFC 5545 folding rejoins WITHOUT adding a space (the leading space is the fold marker).
    assert events[1].summary == "Long title that is foldedacross two lines"
    assert "\n" not in events[1].summary


def test_parse_ics_ignores_eventless_or_undated() -> None:
    assert parse_ics("BEGIN:VCALENDAR\nEND:VCALENDAR") == []
    # a VEVENT with no DTSTART is skipped (can't place it on a timeline)
    assert parse_ics("BEGIN:VEVENT\nUID:x\nSUMMARY:no date\nEND:VEVENT") == []


def test_ha_changed_emits_only_on_real_change() -> None:
    ha._last_state.clear()
    assert ha._changed("light.office", "on") == ""      # first observation
    assert ha._changed("light.office", "on") is None     # unchanged → no event
    assert ha._changed("light.office", "off") == "on"    # changed → previous returned
