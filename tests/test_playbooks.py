"""Playbook unit tests — model + agent injection helper. No DB/model."""

from jarvis.agents.infrastructure import _playbook_section
from jarvis.playbooks.models import Playbook


def test_playbook_id_prefix() -> None:
    pb = Playbook(title="t", procedure="restart x")
    assert pb.id.startswith("pb_")
    assert pb.when_to_use == ""  # optional


def test_playbook_section_renders_hits() -> None:
    pbs = [
        Playbook(title="VPN stack", procedure="restart gluetun first"),
        Playbook(title="DB", procedure="check disk before restart"),
    ]
    section = _playbook_section(pbs)
    assert section.startswith("\n\nRelevant playbooks:")
    assert "VPN stack: restart gluetun first" in section
    assert "DB: check disk before restart" in section


def test_playbook_section_empty() -> None:
    assert _playbook_section([]) == ""
