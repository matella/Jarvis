"""P5 playbooks integration: store + cosine retrieval round-trip."""

from __future__ import annotations

import psycopg
import pytest

from jarvis.playbooks.models import Playbook
from jarvis.playbooks.repository import add_playbook, list_playbooks, search_playbooks

pytestmark = pytest.mark.integration


def test_playbook_store_and_search(db_conn: psycopg.Connection) -> None:
    near = [1.0] + [0.0] * 767
    far = [0.0, 1.0] + [0.0] * 766
    pb_near = Playbook(title="VPN stack", when_to_use="media container down",
                       procedure="restart gluetun, then the dependent container")
    pb_far = Playbook(title="DB", when_to_use="postgres slow", procedure="check disk")
    try:
        add_playbook(db_conn, pb_near, near)
        add_playbook(db_conn, pb_far, far)

        hits = search_playbooks(db_conn, near, k=1)
        assert hits and hits[0][0].id == pb_near.id
        assert hits[0][0].procedure.startswith("restart gluetun")

        titles = {p.title for p in list_playbooks(db_conn)}
        assert {"VPN stack", "DB"} <= titles
    finally:
        db_conn.execute("DELETE FROM playbooks WHERE id = ANY(%s)", ([pb_near.id, pb_far.id],))
