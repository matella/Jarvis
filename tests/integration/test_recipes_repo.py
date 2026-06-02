"""Recipes repository round-trip against a live DB (index=False)."""

from __future__ import annotations

import psycopg
import pytest

from jarvis.recipes import repository
from jarvis.recipes.models import Ingredient, Recipe

pytestmark = pytest.mark.integration


def test_crud_lifecycle(db_conn: psycopg.Connection) -> None:
    db_conn.execute("DELETE FROM recipes")
    recipe = Recipe(
        title="Omelette", servings=1,
        ingredients=[Ingredient(name="egg", quantity="2"), Ingredient(name="butter")],
        steps=["beat", "fry"], tags=["quick"],
    )
    repository.create(db_conn, recipe, index=False)

    got = repository.get(db_conn, recipe.id)
    assert got is not None and got.title == "Omelette"
    assert [i.name for i in got.ingredients] == ["egg", "butter"] and got.steps == ["beat", "fry"]

    repository.update(db_conn, recipe.id, servings=2, notes_md="double it", index=False)
    assert repository.get(db_conn, recipe.id).servings == 2

    assert [r.id for r in repository.recent(db_conn)] == [recipe.id]
    assert repository.delete(db_conn, recipe.id, index=False) is True
    assert repository.get(db_conn, recipe.id).archived is True
    assert repository.recent(db_conn) == []
