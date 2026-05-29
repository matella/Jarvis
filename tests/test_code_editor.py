"""Code-edit executor validation + proposal parsing — no SSH/DB/model."""

import pytest

from jarvis.agents.code_editor import CodeEditProposal, _parse
from jarvis.config import get_settings
from jarvis.tools.contract import Rollback
from jarvis.tools.registry import _validate_content, _validate_path, get_tool


def test_code_edit_file_registered_with_contract() -> None:
    tool = get_tool("code.edit_file")
    assert tool is not None
    assert tool.side_effects is True
    assert tool.idempotent is True
    assert tool.rollback is Rollback.manual
    assert "code:write" in tool.permissions


def test_validate_path_inside_root_ok() -> None:
    root = get_settings().code_repo_path
    assert _validate_path({"path": f"{root}/media/gluetun/docker-compose.yml"}).startswith(root)


def test_validate_path_rejects_escape_and_outside() -> None:
    root = get_settings().code_repo_path
    with pytest.raises(ValueError):
        _validate_path({"path": f"{root}/../etc/passwd"})
    with pytest.raises(ValueError):
        _validate_path({"path": "/etc/passwd"})
    with pytest.raises(ValueError):
        _validate_path({"path": ""})


def test_validate_content_rejects_empty_and_bad_yaml() -> None:
    with pytest.raises(ValueError):
        _validate_content("/x/compose.yml", "   ")
    with pytest.raises(ValueError, match="valid YAML"):
        _validate_content("/x/compose.yml", "services:\n  a:\n   - bad\n  : :")
    # valid yaml passes
    _validate_content("/x/compose.yml", "services:\n  a:\n    image: nginx\n")
    # non-yaml file: only the empty check applies
    _validate_content("/x/run.sh", "echo hi\n")


def test_proposal_parse_and_reject() -> None:
    good = (
        '{"new_content": "services: {}", "summary": "x", '
        '"confidence": 0.8, "risk": "low", "reversible": true}'
    )
    p = _parse(good)
    assert isinstance(p, CodeEditProposal) and p.new_content == "services: {}"
    with pytest.raises(ValueError):
        _parse("not json")
    bad_confidence = (
        '{"new_content": "x", "summary": "y", '
        '"confidence": 9, "risk": "low", "reversible": true}'
    )
    with pytest.raises(ValueError):
        _parse(bad_confidence)
