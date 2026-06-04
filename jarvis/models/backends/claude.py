"""Claude backend — `claude -p` as a caged text-in/text-out endpoint, normalized to the Ollama dict.

Maximum cage (Hard Rule #1): no tools (`--allowedTools ""`), no MCP (no `--mcp-config`), no FS — run
in an empty temp cwd so no CLAUDE.md is read. Auth via CLAUDE_CODE_OAUTH_TOKEN, inherited from the
container env. Output normalizes to the same dict shape every caller already consumes.
"""

from __future__ import annotations

import json
import subprocess
import tempfile


class ClaudeBackendError(Exception):
    """A typed Claude failure carrying a FailureClass-compatible `failure_class`."""

    def __init__(self, failure_class: str, message: str) -> None:
        super().__init__(message)
        self.failure_class = failure_class


def _strip_tool_sections(system: str) -> str:
    """Drop the gated WHAT YOU CAN DO block (tools Claude can't call — noise), but KEEP WHAT YOU CAN
    OBSERVE so Claude knows its data sources (weather, mail, calendar, homelab) and doesn't deny
    them. Identity + senses are what keep Claude answering as Jarvis, not as Claude Code."""
    keep = []
    for block in system.split("\n\n"):
        if block.lstrip().upper().startswith("WHAT YOU CAN DO"):
            continue
        keep.append(block)
    return "\n\n".join(keep)


def _system_text(messages: list[dict]) -> str:
    """The persona/identity → passed via `--system-prompt` so it REPLACES Claude Code's default
    coding-assistant identity (the source of 'working directory'/'repo access' confabulation)."""
    blocks = [_strip_tool_sections(str(m.get("content", "")))
              for m in messages if m.get("role") == "system"]
    return "\n\n".join(b for b in blocks if b.strip())


def _serialize_prompt(messages: list[dict], *, fmt: dict | str | None) -> str:
    """The conversation (non-system turns) → the `-p` prompt; system goes via --system-prompt.
    Appends a schema instruction if `fmt` is given."""
    parts = [f"{m.get('role', 'user').capitalize()}: {m.get('content', '')}"
             for m in messages if m.get("role") != "system"]
    prompt = "\n\n".join(parts)
    if fmt is not None:
        prompt += ("\n\nRespond with ONLY a JSON object matching this schema (no prose, no "
                   f"markdown fences):\n{json.dumps(fmt)}")
    return prompt


def _classify(returncode: int, stderr: str) -> str:
    s = (stderr or "").lower()
    if returncode == 124:
        return "timeout"
    if "rate limit" in s or "usage limit" in s or "overloaded" in s:
        return "resource_exhaustion"
    if "not logged in" in s or "unauthorized" in s or "/login" in s:
        return "permission_denied"
    if "command not found" in s or "no such file" in s:
        return "tool_unavailable"
    return "unknown"


def claude_backend(
    role: str, messages: list[dict], *, fmt: dict | str | None, timeout: int
) -> dict:
    """Run one caged `claude -p` completion and normalize to the Ollama dict shape."""
    from jarvis.config import get_settings

    s = get_settings()
    cmd = ["claude", "-p", _serialize_prompt(messages, fmt=fmt),
           "--allowedTools", "", "--output-format", "text"]
    system = _system_text(messages)
    if system:
        # Replace Claude Code's built-in identity with Jarvis's, and drop its dynamic system
        # sections (cwd/git/env) — those cause "the working directory is empty" type confabulation.
        cmd += ["--system-prompt", system, "--exclude-dynamic-system-prompt-sections"]
    if s.claude_model:
        cmd += ["--model", s.claude_model]
    try:
        with tempfile.TemporaryDirectory() as cwd:  # empty cwd → no CLAUDE.md pickup
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
    except subprocess.TimeoutExpired as exc:
        raise ClaudeBackendError("timeout", str(exc)) from exc
    except FileNotFoundError as exc:
        raise ClaudeBackendError("tool_unavailable", str(exc)) from exc
    if proc.returncode != 0:
        raise ClaudeBackendError(_classify(proc.returncode, proc.stderr),
                                 proc.stderr or "claude failed")
    text = proc.stdout.strip()
    if "not logged in" in text.lower():  # CLI prints this to stdout, exit 0
        raise ClaudeBackendError("permission_denied", text)
    return {"message": {"content": text}, "model": s.claude_model or "claude",
            "backend_used": "claude", "eval_count": 0, "prompt_eval_count": 0}
