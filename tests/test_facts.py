"""Durable-fact model validation — pure (no DB). Repo round-trip is in integration."""

from __future__ import annotations

import pytest

from jarvis.memory.facts import UserFact


def test_key_is_normalized() -> None:
    assert UserFact(key="  My City ", value="Brussels").key == "my_city"


def test_value_is_sanitized_and_capped() -> None:
    # sanitize() redacts secrets in operator prose; empty after stripping is rejected.
    f = UserFact(key="note", value="  plain text  ")
    assert f.value == "plain text"
    with pytest.raises(ValueError):
        UserFact(key="x", value="   ")


def test_blank_or_oversized_key_rejected() -> None:
    with pytest.raises(ValueError):
        UserFact(key="   ", value="v")
    with pytest.raises(ValueError):
        UserFact(key="k" * 65, value="v")
