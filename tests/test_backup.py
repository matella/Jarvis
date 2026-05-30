"""Durability unit tests — backup retention selection. No DB/docker."""

from jarvis.ops.backup import _files_to_prune


def test_retention_keeps_newest_n() -> None:
    files = [
        "jarvis-20260101T000000Z.sql.gz",
        "jarvis-20260103T000000Z.sql.gz",
        "jarvis-20260102T000000Z.sql.gz",
        "jarvis-20260104T000000Z.sql.gz",
    ]
    prune = _files_to_prune(files, keep=2)
    # newest two kept (04, 03); oldest two pruned (02, 01)
    assert sorted(prune) == [
        "jarvis-20260101T000000Z.sql.gz",
        "jarvis-20260102T000000Z.sql.gz",
    ]


def test_retention_keep_all_when_under_limit() -> None:
    files = ["jarvis-20260101T000000Z.sql.gz"]
    assert _files_to_prune(files, keep=14) == []
