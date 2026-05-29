"""Tool contract + capability registry unit tests."""

from jarvis.tools.contract import Rollback
from jarvis.tools.registry import capabilities, get_tool, valid_intent_types


def test_restart_container_capability_contract() -> None:
    tool = get_tool("docker.restart_container")
    assert tool is not None
    assert tool.side_effects is True
    assert tool.idempotent is False
    assert tool.rollback is Rollback.none
    assert tool.timeout_seconds == 30
    assert "docker:restart" in tool.permissions


def test_unknown_type_has_no_tool() -> None:
    assert get_tool("docker.delete_everything") is None


def test_valid_intent_types_include_capabilities_and_advisory() -> None:
    valid = valid_intent_types()
    assert "docker.restart_container" in valid
    assert "infra.investigate" in valid
    assert "infra.recommend" in valid


def test_capabilities_lists_registered_tools() -> None:
    assert "docker.restart_container" in capabilities()
