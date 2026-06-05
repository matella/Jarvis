"""Wave 5 — exact-compute (#21): safe evaluation + strict detection."""

from __future__ import annotations

import pytest

from jarvis.agents import calc


@pytest.mark.parametrize("expr,expected", [
    ("12 * (3 + 4)", "84"),
    ("2^10", "1024"),
    ("100 / 8", "12.5"),
    ("17 % 5", "2"),
    ("2 ** 0.5", "1.41421"),
])
def test_evaluate_and_compute(expr: str, expected: str) -> None:
    assert calc.compute(f"what is {expr}?") == expected


def test_whitelisted_functions_evaluate() -> None:
    # functions work in evaluate() even though the strict detector won't auto-route them
    assert calc.evaluate("sqrt(144)") == 12
    assert calc.evaluate("factorial(5)") == 120


def test_percent_of() -> None:
    assert calc.compute("what is 15% of 80") == "12"


def test_detects_only_real_math() -> None:
    assert calc.looks_like_math("what is 12 * 7")
    assert calc.looks_like_math("calculate (5+3)/2")
    assert calc.looks_like_math("15% of 200")
    # NOT math — must fall through to the model:
    assert not calc.looks_like_math("what is the capital of France")
    assert not calc.looks_like_math("reverse a string in python")
    assert not calc.looks_like_math("what is 5")            # no operator → not a calc
    assert not calc.looks_like_math("what's the time complexity of quicksort")


def test_rejects_unsafe_expressions() -> None:
    # No names/calls outside the math whitelist, no attribute access — compute returns None.
    assert calc.compute("__import__('os').system('ls')") is None
    assert calc.compute("what is 1/0") is None              # ZeroDivisionError → None (safe)
