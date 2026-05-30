"""Speech-to-text via Whisper.cpp. Audio (WAV bytes) → text.

A thin subprocess wrapper. Command construction + output parsing are pure (unit-tested); the actual
binary call is isolated. `available()` lets the gateway degrade gracefully when no model is set.
"""

from __future__ import annotations

import re
import subprocess
import tempfile

from jarvis.config import get_settings


class STTUnavailable(Exception):
    """Whisper binary/model not configured or not runnable."""


def available() -> bool:
    s = get_settings()
    return bool(s.whisper_model)


def _build_command(wav_path: str) -> list[str]:
    s = get_settings()
    # whisper.cpp: -m model -f file -nt (no timestamps) -otxt would write a file; we read stdout.
    return [s.whisper_bin, "-m", s.whisper_model, "-f", wav_path, "-nt"]


# whisper.cpp prints lines like "[00:00.000 --> 00:02.000]  text" or, with -nt, plain text lines.
_TS = re.compile(r"^\s*\[[0-9:.\s>-]+\]\s*")


def parse_output(stdout: str) -> str:
    """Extract the transcript from whisper.cpp stdout (strip any timestamp prefixes)."""
    lines = [_TS.sub("", ln).strip() for ln in stdout.splitlines()]
    return " ".join(ln for ln in lines if ln).strip()


def transcribe(wav: bytes) -> str:
    """Transcribe WAV audio to text. Raises STTUnavailable if the backend isn't ready."""
    s = get_settings()
    if not s.whisper_model:
        raise STTUnavailable("whisper_model not configured")
    with tempfile.NamedTemporaryFile(suffix=".wav") as fh:
        fh.write(wav)
        fh.flush()
        try:
            proc = subprocess.run(
                _build_command(fh.name), capture_output=True, text=True, timeout=120, check=True,
            )
        except FileNotFoundError as exc:
            raise STTUnavailable(f"whisper binary not found: {s.whisper_bin}") from exc
        except subprocess.CalledProcessError as exc:
            raise STTUnavailable(f"whisper failed: {exc.stderr or exc}") from exc
    return parse_output(proc.stdout)
