"""Execute-to-verify (Wave 1.2) — run model-generated Python in a throwaway, isolated container.

The next step past syntax-checking (Wave 2): actually RUN a self-contained snippet to catch runtime
and logic errors, then feed the real traceback back to the coder for one fix. Isolation is the whole
point — each run is `docker run --rm --network none --read-only --cap-drop ALL` as a non-root user
with a memory cap, pid cap, a small tmpfs for /tmp, and a hard timeout. No host filesystem, no
network, no secrets, no privileges. OFF by default (config opt-in). Best-effort: if Docker is absent
or the run can't start, we return `ran=False` and the caller simply skips verification — it never
crashes a turn and never blocks the answer. This does NOT touch infrastructure; it is a scratch
sandbox for verifying code the operator asked about, fully separate from the deterministic executor.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

from jarvis.agents.code_validation import extract_code_blocks

_PY_LANGS = {"py", "python", "python3"}
_TRACEBACK_MARKER = "Traceback (most recent call last)"


@dataclass(frozen=True)
class RunResult:
    ran: bool          # False → sandbox unavailable/disabled/skipped (no verdict)
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


def exec_enabled() -> bool:
    from jarvis.config import get_settings

    return bool(get_settings().code_exec_enabled)


def runnable_python(blocks: list[tuple[str, str]]) -> str | None:
    """The python block worth running: the longest one that looks self-contained. Skips snippets
    that block on input() (would just hit the timeout) or are trivially empty."""
    candidates = [code for lang, code in blocks if lang in _PY_LANGS and code.strip()]
    candidates = [c for c in candidates if "input(" not in c]
    if not candidates:
        return None
    return max(candidates, key=len)


def _docker_cmd(image: str, mem: str) -> list[str]:
    # Maximum cage: no network, read-only rootfs, all caps dropped, non-root, no privilege
    # escalation, small writable tmpfs for /tmp, capped memory + pids. Code arrives on stdin.
    return [
        "docker", "run", "--rm", "-i",
        "--network", "none",
        "--read-only",
        "--tmpfs", "/tmp:size=16m,exec",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--user", "65534:65534",
        "--memory", mem, "--memory-swap", mem,
        "--pids-limit", "128",
        "--cpus", "1",
        image, "python", "-",
    ]


def run_python(code: str) -> RunResult:
    """Run `code` in the sandbox container. ran=False on any infrastructure problem (Docker missing,
    image absent, daemon unreachable) — verification is best-effort and must never break a turn."""
    from jarvis.config import get_settings

    s = get_settings()
    if not s.code_exec_enabled:
        return RunResult(ran=False)
    cmd = _docker_cmd(s.code_exec_image, s.code_exec_memory)
    try:
        proc = subprocess.run(
            cmd, input=code, capture_output=True, text=True,
            timeout=s.code_exec_timeout_s,
        )
    except subprocess.TimeoutExpired:
        return RunResult(ran=True, exit_code=124, timed_out=True,
                         stderr="(execution timed out)")
    except (FileNotFoundError, OSError):
        return RunResult(ran=False)  # docker not installed / not runnable here
    return RunResult(ran=True, exit_code=proc.returncode,
                     stdout=proc.stdout, stderr=proc.stderr)


def failure_feedback(result: RunResult) -> str | None:
    """A short failure description to feed back to the coder, or None if the run looks fine.

    Only a genuine error counts (a Python traceback, or a timeout) — a clean exit is a pass, and a
    skipped run (ran=False) yields no feedback so illustrative snippets aren't punished."""
    if not result.ran:
        return None
    if result.timed_out:
        return "The code did not finish within the time limit (possible infinite loop or blocking)."
    if _TRACEBACK_MARKER in result.stderr:
        tail = result.stderr.strip().splitlines()[-12:]
        return "When run, the code raised:\n" + "\n".join(tail)
    return None


def verify(markdown: str) -> str | None:
    """Extract the runnable python from an answer, run it sandboxed, return failure feedback (or
    None: disabled, nothing runnable, sandbox unavailable, or it ran clean)."""
    if not exec_enabled():
        return None
    code = runnable_python(extract_code_blocks(markdown))
    if not code:
        return None
    return failure_feedback(run_python(code))
