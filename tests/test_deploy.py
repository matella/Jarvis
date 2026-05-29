"""Deploy-detection unit tests — pure _diff logic, no docker/DB."""

from jarvis.ingest.deploy import _diff


def test_first_sighting_seeds_baseline_no_deploy() -> None:
    current = [("container:a", "nginx:1.0", "sha256:aaa")]
    assert _diff(current, baseline={}) == []  # unknown container → seed only


def test_unchanged_digest_no_deploy() -> None:
    current = [("container:a", "nginx:1.0", "sha256:aaa")]
    baseline = {"container:a": ("nginx:1.0", "sha256:aaa")}
    assert _diff(current, baseline) == []


def test_digest_change_is_a_deploy() -> None:
    current = [("container:a", "nginx:1.1", "sha256:bbb")]
    baseline = {"container:a": ("nginx:1.0", "sha256:aaa")}
    changes = _diff(current, baseline)
    assert changes == [("container:a", "nginx:1.1", "sha256:bbb", "nginx:1.0", "sha256:aaa")]


def test_same_tag_new_digest_is_a_deploy() -> None:
    # :latest re-pulled to a new digest is still a redeploy
    current = [("container:a", "app:latest", "sha256:new")]
    baseline = {"container:a": ("app:latest", "sha256:old")}
    changes = _diff(current, baseline)
    assert len(changes) == 1 and changes[0][2] == "sha256:new"


def test_only_changed_containers_reported() -> None:
    current = [
        ("container:a", "nginx:1.1", "sha256:bbb"),  # changed
        ("container:b", "redis:7", "sha256:ccc"),    # unchanged
    ]
    baseline = {
        "container:a": ("nginx:1.0", "sha256:aaa"),
        "container:b": ("redis:7", "sha256:ccc"),
    }
    changes = _diff(current, baseline)
    assert [c[0] for c in changes] == ["container:a"]
