"""Recipes repository — CRUD + awareness + search + read accessors."""

from __future__ import annotations

import psycopg
from psycopg.types.json import Json

from jarvis.events.models import utcnow
from jarvis.modules import search
from jarvis.modules.awareness import emit_awareness
from jarvis.recipes.models import Ingredient, Recipe

_SOURCE = "recipes"
_COLS = (
    "id, title, source_url, servings, ingredients_json, steps_json, tags, notes_md, "
    "archived, schema_version, created_at, updated_at"
)


def _row_to_recipe(row: dict) -> Recipe:
    ingredients = [Ingredient(**i) for i in (row.pop("ingredients_json") or [])]
    steps = list(row.pop("steps_json") or [])
    return Recipe(ingredients=ingredients, steps=steps, **row)


def _index(recipe: Recipe) -> None:
    search.index_entity(source=_SOURCE, entity_ref=recipe.entity_ref, title=recipe.title,
                        text=recipe.search_text())


def create(conn: psycopg.Connection, recipe: Recipe, *, correlation_id: str | None = None,
           index: bool = True, imported: bool = False) -> Recipe:
    conn.execute(
        f"INSERT INTO recipes ({_COLS}) VALUES "
        "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            recipe.id, recipe.title, recipe.source_url, recipe.servings,
            Json([i.model_dump() for i in recipe.ingredients]), Json(recipe.steps),
            recipe.tags, recipe.notes_md, recipe.archived, recipe.schema_version,
            recipe.created_at, recipe.updated_at,
        ),
    )
    emit_awareness("recipe.imported" if imported else "recipe.created", source=_SOURCE,
                   entity_ref=recipe.entity_ref, correlation_id=correlation_id, title=recipe.title)
    if index:
        _index(recipe)
    return recipe


def get(conn: psycopg.Connection, recipe_id: str) -> Recipe | None:
    row = conn.execute(f"SELECT {_COLS} FROM recipes WHERE id = %s", (recipe_id,)).fetchone()
    return _row_to_recipe(row) if row else None


def update(conn: psycopg.Connection, recipe_id: str, *, title: str | None = None,
           servings: int | None = None, notes_md: str | None = None,
           tags: list[str] | None = None, index: bool = True) -> Recipe | None:
    current = get(conn, recipe_id)
    if current is None:
        return None
    candidates = {"title": title, "servings": servings, "notes_md": notes_md, "tags": tags}
    merged = current.model_copy(update={k: v for k, v in candidates.items() if v is not None})
    merged = Recipe(**merged.model_dump()).model_copy(update={"updated_at": utcnow()})
    conn.execute(
        "UPDATE recipes SET title=%s, servings=%s, notes_md=%s, tags=%s, updated_at=%s WHERE id=%s",
        (merged.title, merged.servings, merged.notes_md, merged.tags, merged.updated_at, recipe_id),
    )
    emit_awareness("recipe.updated", source=_SOURCE, entity_ref=merged.entity_ref,
                   title=merged.title)
    if index:
        _index(merged)
    return merged


def delete(conn: psycopg.Connection, recipe_id: str, *, index: bool = True) -> bool:
    current = get(conn, recipe_id)
    if current is None:
        return False
    conn.execute("UPDATE recipes SET archived=true, updated_at=%s WHERE id=%s",
                 (utcnow(), recipe_id))
    emit_awareness("recipe.archived", source=_SOURCE, entity_ref=current.entity_ref,
                   title=current.title)
    if index:
        search.purge_entity(current.entity_ref)
    return True


def recent(conn: psycopg.Connection, *, limit: int = 50) -> list[Recipe]:
    rows = conn.execute(
        f"SELECT {_COLS} FROM recipes WHERE archived = false ORDER BY updated_at DESC LIMIT %s",
        (limit,),
    ).fetchall()
    return [_row_to_recipe(r) for r in rows]
