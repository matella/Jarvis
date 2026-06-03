"""Model-pref persistence — upsert/get/list + apply a named preset (emits model.pref_changed)."""

from __future__ import annotations

import psycopg
from psycopg.types.json import Json

from jarvis.cookbook.models import PRESETS, ModelPref, PrefScope
from jarvis.events.models import utcnow
from jarvis.modules.awareness import emit_awareness

_COLS = (
    "id, scope, scope_key, backend, model, params_json, preset_name, "
    "schema_version, created_at, updated_at"
)


def _row_to_pref(row: dict) -> ModelPref:
    return ModelPref(params=row.pop("params_json") or {}, **row)


def set_pref(conn: psycopg.Connection, pref: ModelPref) -> ModelPref:
    pref = pref.model_copy(update={"updated_at": utcnow()})
    conn.execute(
        f"INSERT INTO model_prefs ({_COLS}) VALUES "
        "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (scope, scope_key) DO UPDATE SET backend=EXCLUDED.backend, "
        "model=EXCLUDED.model, params_json=EXCLUDED.params_json, "
        "preset_name=EXCLUDED.preset_name, updated_at=EXCLUDED.updated_at",
        (pref.id, pref.scope.value, pref.scope_key, pref.backend, pref.model, Json(pref.params),
         pref.preset_name, pref.schema_version, pref.created_at, pref.updated_at),
    )
    emit_awareness("model.pref_changed", source="cookbook",
                   entity_ref=f"modelpref:{pref.scope_key}", scope=pref.scope.value,
                   scope_key=pref.scope_key, backend=pref.backend)
    return pref


def get_action_pref(conn: psycopg.Connection, action_key: str) -> ModelPref | None:
    row = conn.execute(
        f"SELECT {_COLS} FROM model_prefs WHERE scope = 'action' AND scope_key = %s",
        (action_key,),
    ).fetchone()
    return _row_to_pref(row) if row else None


def list_prefs(conn: psycopg.Connection) -> list[ModelPref]:
    rows = conn.execute(f"SELECT {_COLS} FROM model_prefs ORDER BY scope, scope_key").fetchall()
    return [_row_to_pref(r) for r in rows]


def apply_preset(conn: psycopg.Connection, name: str) -> int:
    """Write the per-action rows for a named preset. Returns the number of actions set."""
    mapping = PRESETS.get(name)
    if mapping is None:
        raise ValueError(f"unknown preset: {name!r} (have {', '.join(PRESETS)})")
    for action_key, backend in mapping.items():
        set_pref(conn, ModelPref(scope=PrefScope.action, scope_key=action_key,
                                 backend=backend, preset_name=name))
    return len(mapping)
