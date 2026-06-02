"""Calendar repository — local CRUD (truth) + mirror upsert + read-only guard + agenda. Live DB."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from jarvis.calendar import repository
from jarvis.calendar.models import CalendarEvent, EventSource

pytestmark = pytest.mark.integration

_T0 = datetime(2026, 6, 2, 9, 0, tzinfo=UTC)


def test_local_crud_and_mirror_read_only(db_conn: psycopg.Connection) -> None:
    db_conn.execute("DELETE FROM calendar_events")
    local = CalendarEvent(title="Dentist", starts_at=_T0, ends_at=_T0 + timedelta(hours=1))
    repository.create_local(db_conn, local, index=False)
    repository.update_local(db_conn, local.id, location="Clinic", index=False)
    assert repository.get(db_conn, local.id).location == "Clinic"

    mirror = CalendarEvent(source=EventSource.google, external_uid="g1", title="Standup",
                           starts_at=_T0 + timedelta(days=1))
    repository.upsert_mirror(db_conn, mirror)
    # re-sync same uid → no duplicate
    repository.upsert_mirror(db_conn, mirror.model_copy(update={"title": "Standup (moved)"}))
    fetched = repository.agenda(db_conn, _T0 - timedelta(days=1), _T0 + timedelta(days=2))
    assert sum(1 for e in fetched if e.external_uid == "g1") == 1

    # editing a mirror event is refused
    mirror_row = next(e for e in fetched if e.external_uid == "g1")
    with pytest.raises(ValueError):
        repository.update_local(db_conn, mirror_row.id, title="nope", index=False)
    with pytest.raises(ValueError):
        repository.delete_local(db_conn, mirror_row.id, index=False)

    assert repository.delete_local(db_conn, local.id, index=False) is True
