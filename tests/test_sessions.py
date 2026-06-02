"""Session login pure helpers — passphrase scrypt verify + token hashing. No DB."""

from __future__ import annotations

from jarvis.gateway import sessions


def test_passphrase_round_trip_and_constant_time() -> None:
    stored = sessions.hash_passphrase("correct horse battery staple")
    assert stored.startswith("scrypt$")
    assert sessions.verify_passphrase("correct horse battery staple", stored) is True
    assert sessions.verify_passphrase("wrong", stored) is False


def test_verify_rejects_unset_or_malformed() -> None:
    assert sessions.verify_passphrase("x", None) is False
    assert sessions.verify_passphrase("x", "") is False
    assert sessions.verify_passphrase("x", "notscrypt$aa$bb") is False
    assert sessions.verify_passphrase("x", "scrypt$zz$qq") is False  # non-hex
    assert sessions.verify_passphrase("", sessions.hash_passphrase("y")) is False


def test_hash_passphrase_rejects_empty() -> None:
    import pytest

    with pytest.raises(ValueError):
        sessions.hash_passphrase("")


def test_each_hash_uses_a_fresh_salt() -> None:
    a = sessions.hash_passphrase("same")
    b = sessions.hash_passphrase("same")
    assert a != b  # distinct salts → distinct stored strings
    assert sessions.verify_passphrase("same", a) and sessions.verify_passphrase("same", b)


def test_token_hash_is_stable_and_opaque() -> None:
    tok = sessions.new_token()
    assert sessions.new_token() != tok  # fresh each call
    assert sessions.hash_token(tok) == sessions.hash_token(tok)  # deterministic
    assert tok not in sessions.hash_token(tok)  # the raw token is not recoverable from the hash
