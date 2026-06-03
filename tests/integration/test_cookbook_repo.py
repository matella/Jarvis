"""Model-pref repository round-trip + preset application against a live DB."""

from __future__ import annotations

import psycopg
import pytest

from jarvis.cookbook import api, repository
from jarvis.cookbook.models import ModelPref, PrefScope

pytestmark = pytest.mark.integration


def test_set_get_and_preset(db_conn: psycopg.Connection) -> None:
    db_conn.execute("DELETE FROM model_prefs")
    repository.set_pref(db_conn, ModelPref(scope=PrefScope.action,
                                           scope_key="research.synthesize", backend="claude"))
    assert api.backend_for(db_conn, "research.synthesize") == "claude"
    assert api.backend_for(db_conn, "unset", default="local") == "local"

    # upsert (no duplicate) — flip to local
    repository.set_pref(db_conn, ModelPref(scope=PrefScope.action,
                                           scope_key="research.synthesize", backend="local"))
    assert api.backend_for(db_conn, "research.synthesize") == "local"

    n = repository.apply_preset(db_conn, "quality")
    assert n == 5
    assert api.backend_for(db_conn, "postmortem") == "claude"
    assert {p.scope_key for p in repository.list_prefs(db_conn)} >= set(
        ["research.synthesize", "postmortem"]
    )
    with pytest.raises(ValueError):
        repository.apply_preset(db_conn, "nope")
