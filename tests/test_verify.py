"""Backlog #1 unit: outcome-verification classification + target derivation (pure)."""

from __future__ import annotations

from jarvis.verify.checks import VerifyStatus, classify_container_recovery, container_target


def test_verified_when_running_and_no_failures() -> None:
    assert classify_container_recovery("running", 0) is VerifyStatus.verified


def test_unverified_when_failed_again() -> None:
    assert classify_container_recovery("running", 2) is VerifyStatus.unverified  # fresh failures
    assert classify_container_recovery("exited", 0) is VerifyStatus.unverified   # still down


def test_inconclusive_when_status_unknown() -> None:
    assert classify_container_recovery(None, 0) is VerifyStatus.inconclusive
    assert classify_container_recovery("", 0) is VerifyStatus.inconclusive


def test_container_target_derivation() -> None:
    assert container_target({"container": "nginx"}) == "container:nginx"
    assert container_target({"entity": "light.office"}) is None  # not a container action
    assert container_target({}) is None
