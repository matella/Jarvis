"""Robust ssh invocation to the host (REMOTE_SSH) — shared by GPU telemetry and backups.

The daemon runs in a container with the operator's ~/.ssh mounted READ-ONLY, so: BatchMode (never
prompt), accept-new host keys written to /tmp (the mount can't be written), short connect timeout.
"""

from __future__ import annotations

_SSH_OPTS = [
    "-o", "BatchMode=yes",
    "-o", "StrictHostKeyChecking=accept-new",
    "-o", "UserKnownHostsFile=/tmp/.known_hosts",
    "-o", "ConnectTimeout=5",
]


def ssh_cmd(target: str, remote_command: str) -> list[str]:
    """The argv for `ssh <target> <remote_command>` with the container-safe options."""
    return ["ssh", *_SSH_OPTS, target, remote_command]
