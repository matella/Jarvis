"""Recipes — model, URL import (mocked fetch+chat), deterministic scaler, tool gating. No DB/net."""

from __future__ import annotations

import json

import pytest

import jarvis.recipes.tools  # noqa: F401 — registers recipe.* for the gating assertions
from jarvis.recipes.importer import import_recipe, scale_servings
from jarvis.recipes.models import Ingredient, Recipe
from jarvis.tools.registry import get_tool


def test_recipe_validation() -> None:
    r = Recipe(
        title="  Pancakes  ",
        ingredients=[Ingredient(name="flour", quantity="200", unit="g")],
        steps=["mix", "  ", "cook"], tags=["Breakfast", "breakfast"],
    )
    assert r.title == "Pancakes" and r.steps == ["mix", "cook"] and r.tags == ["breakfast"]
    assert r.entity_ref == f"recipe:{r.id}"
    with pytest.raises(ValueError):
        Ingredient(name="  ")


def test_import_recipe_one_shot(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "title": "Tomato Soup", "servings": 4,
        "ingredients": [{"name": "tomato", "quantity": "6", "unit": ""}],
        "steps": ["blend", "heat"],
    }
    calls: list[dict] = []

    def chat(role, messages, **kwargs):
        calls.append(kwargs)
        return {"message": {"content": json.dumps(payload)}}

    recipe = import_recipe(
        "http://recipes.example/soup",
        fetch_fn=lambda url: "<html>tomato soup ...</html>",
        chat_fn=chat,
    )
    assert recipe.title == "Tomato Soup" and recipe.servings == 4
    assert recipe.source_url == "http://recipes.example/soup"
    assert recipe.ingredients[0].name == "tomato"
    assert len(calls) == 1 and calls[0].get("format") is not None  # exactly one grammar inference


def test_import_recipe_rejects_unparseable(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError):
        import_recipe("http://x", fetch_fn=lambda u: "junk",
                      chat_fn=lambda *a, **k: {"message": {"content": "not json"}})


def test_scale_servings_is_deterministic() -> None:
    r = Recipe(title="X", servings=2, ingredients=[
        Ingredient(name="flour", quantity="200", unit="g"),
        Ingredient(name="egg", quantity="1", unit=""),
        Ingredient(name="salt", quantity="to taste", unit=""),
    ])
    scaled = scale_servings(r, 4)
    assert scaled.servings == 4
    assert scaled.ingredients[0].quantity == "400"     # 200 * 2
    assert scaled.ingredients[1].quantity == "2"       # 1 * 2
    assert scaled.ingredients[2].quantity == "to taste"  # non-numeric untouched
    with pytest.raises(ValueError):
        scale_servings(r, 0)


def test_recipe_tools_registered_with_right_gating() -> None:
    for name in ("recipe.create", "recipe.update", "recipe.delete", "recipe.to_shopping_list"):
        assert get_tool(name).side_effects is False     # CRUD + list → auto-run
    assert get_tool("recipe.import_url").side_effects is True  # external fetch → gated
