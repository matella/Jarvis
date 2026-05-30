"""Text-to-speech via Piper. Text → WAV audio bytes.

Thin subprocess wrapper; Piper reads text on stdin and writes a WAV to a path (or stdout). Command
construction is pure (unit-tested). `available()` lets the gateway skip TTS when no voice is set.
"""

from __future__ import annotations

import subprocess
import tempfile

from jarvis.config import get_settings


class TTSUnavailable(Exception):
    """Piper binary/voice not configured or not runnable."""


def available() -> bool:
    return bool(get_settings().piper_voice)


def _build_command(out_path: str) -> list[str]:
    s = get_settings()
    return [s.piper_bin, "--model", s.piper_voice, "--output_file", out_path]


def synthesize(text: str) -> bytes:
    """Render `text` to WAV bytes. Raises TTSUnavailable if the backend isn't ready."""
    s = get_settings()
    if not s.piper_voice:
        raise TTSUnavailable("piper_voice not configured")
    with tempfile.NamedTemporaryFile(suffix=".wav") as fh:
        try:
            subprocess.run(
                _build_command(fh.name), input=text, text=True,
                capture_output=True, timeout=60, check=True,
            )
        except FileNotFoundError as exc:
            raise TTSUnavailable(f"piper binary not found: {s.piper_bin}") from exc
        except subprocess.CalledProcessError as exc:
            raise TTSUnavailable(f"piper failed: {exc.stderr or exc}") from exc
        fh.seek(0)
        return fh.read()
