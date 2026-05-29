"""Infrastructure-agent proposal parsing/validation — no model/DB."""

import pytest

from jarvis.agents.infrastructure import IntentProposal, _parse


def test_parse_valid_restart_proposal() -> None:
    content = (
        '{"type": "docker.restart_container", "target": {"container": "nginx"}, '
        '"summary": "down, restart it", "confidence": 0.9, "risk": "low", "reversible": true}'
    )
    proposal = _parse(content)
    assert isinstance(proposal, IntentProposal)
    assert proposal.type == "docker.restart_container"
    assert proposal.target == {"container": "nginx"}


def test_parse_rejects_unknown_capability() -> None:
    content = (
        '{"type": "docker.delete_everything", "target": {}, "summary": "nope", '
        '"confidence": 0.5, "risk": "high", "reversible": false}'
    )
    with pytest.raises(ValueError, match="not a known capability"):
        _parse(content)


def test_parse_rejects_out_of_range_confidence() -> None:
    content = (
        '{"type": "infra.recommend", "target": {}, "summary": "x", '
        '"confidence": 1.7, "risk": "low", "reversible": true}'
    )
    with pytest.raises(ValueError, match="schema validation"):
        _parse(content)


def test_parse_rejects_non_json() -> None:
    with pytest.raises(ValueError):
        _parse("I think we should restart nginx.")
