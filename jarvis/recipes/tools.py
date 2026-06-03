"""Recipe capability tools — CRUD auto-run; import_url gated (external); shopping-list→tasks."""

from __future__ import annotations

from typing import Any

from jarvis import db
from jarvis.recipes import repository
from jarvis.recipes.importer import import_recipe
from jarvis.recipes.models import Ingredient, Recipe
from jarvis.tasks import repository as tasks_repo
from jarvis.tasks.models import Task
from jarvis.tools.contract import Rollback, Tool
from jarvis.tools.registry import register


def _opt_str(target: dict[str, Any], key: str) -> str | None:
    v = target.get(key)
    return v if isinstance(v, str) and v.strip() else None


def _require_id(target: dict[str, Any]) -> str:
    recipe_id = target.get("id")
    if not isinstance(recipe_id, str) or not recipe_id:
        raise ValueError("recipe id is required")
    return recipe_id


def _ingredients(target: dict[str, Any]) -> list[Ingredient]:
    raw = target.get("ingredients") or []
    out: list[Ingredient] = []
    for item in raw:
        if isinstance(item, dict) and str(item.get("name", "")).strip():
            out.append(Ingredient(name=str(item["name"]), quantity=str(item.get("quantity", "")),
                                   unit=str(item.get("unit", ""))))
        elif isinstance(item, str) and item.strip():
            out.append(Ingredient(name=item.strip()))
    return out


def _create_run(target: dict[str, Any], *, timeout_s: int) -> dict[str, Any]:
    title = _opt_str(target, "title")
    if title is None:
        raise ValueError("recipe title is required")
    servings = target.get("servings")
    recipe = Recipe(
        title=title,
        servings=servings if isinstance(servings, int) else None,
        ingredients=_ingredients(target),
        steps=[str(s) for s in (target.get("steps") or [])],
        notes_md=str(target.get("notes_md") or ""),
    )
    with db.connect() as conn:
        repository.create(conn, recipe)
    return {"id": recipe.id, "entity_ref": recipe.entity_ref}


def _update_run(target: dict[str, Any], *, timeout_s: int) -> dict[str, Any]:
    recipe_id = _require_id(target)
    servings = target.get("servings")
    with db.connect() as conn:
        updated = repository.update(
            conn, recipe_id, title=_opt_str(target, "title"),
            servings=servings if isinstance(servings, int) else None,
            notes_md=target.get("notes_md") if isinstance(target.get("notes_md"), str) else None,
        )
    if updated is None:
        raise ValueError(f"recipe not found: {recipe_id}")
    return {"id": recipe_id}


def _delete_run(target: dict[str, Any], *, timeout_s: int) -> dict[str, Any]:
    recipe_id = _require_id(target)
    with db.connect() as conn:
        ok = repository.delete(conn, recipe_id)
    if not ok:
        raise ValueError(f"recipe not found: {recipe_id}")
    return {"id": recipe_id, "status": "archived"}


def _import_run(target: dict[str, Any], *, timeout_s: int) -> dict[str, Any]:
    url = _opt_str(target, "url")
    if url is None:
        raise ValueError("recipe url is required")
    recipe = import_recipe(url)
    with db.connect() as conn:
        repository.create(conn, recipe, imported=True)
    return {"id": recipe.id, "entity_ref": recipe.entity_ref, "title": recipe.title}


def _to_shopping_list_run(target: dict[str, Any], *, timeout_s: int) -> dict[str, Any]:
    recipe_id = _require_id(target)
    with db.connect() as conn:
        recipe = repository.get(conn, recipe_id)
        if recipe is None:
            raise ValueError(f"recipe not found: {recipe_id}")
        lines = [
            "- " + " ".join(p for p in (i.quantity, i.unit, i.name) if p).strip()
            for i in recipe.ingredients
        ]
        task = Task(
            title=f"Shopping: {recipe.title}",
            notes="\n".join(lines),
            source_entity_ref=recipe.entity_ref,
        )
        tasks_repo.create(conn, task)
    return {"task_id": task.id, "items": len(recipe.ingredients)}


_PERMS = ["recipes:write"]

register(Tool(
    name="recipe.create", version=1, permissions=_PERMS, side_effects=False, idempotent=False,
    max_retries=1, timeout_seconds=5, rollback=Rollback.manual, run=_create_run,
))
register(Tool(
    name="recipe.update", version=1, permissions=_PERMS, side_effects=False, idempotent=True,
    max_retries=1, timeout_seconds=5, rollback=Rollback.manual, run=_update_run,
))
register(Tool(
    name="recipe.delete", version=1, permissions=_PERMS, side_effects=False, idempotent=True,
    max_retries=1, timeout_seconds=5, rollback=Rollback.manual, run=_delete_run,
))
register(Tool(
    name="recipe.import_url", version=1, permissions=["recipes:write", "web:read"],
    side_effects=True,  # external fetch → the agent gates it
    idempotent=False, max_retries=0, timeout_seconds=30, rollback=Rollback.manual, run=_import_run,
))
register(Tool(
    name="recipe.to_shopping_list", version=1, permissions=["recipes:read", "tasks:write"],
    side_effects=False, idempotent=False, max_retries=1, timeout_seconds=5,
    rollback=Rollback.manual, run=_to_shopping_list_run,
))
