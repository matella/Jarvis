"""Wake-word gate — "Hey Jarvis" activates listening; only then do we buffer audio.

The privacy-respecting property: NOTHING is buffered before a wake event (no always-on recording).
After wake, audio frames accumulate until trailing silence exceeds `wake_silence_ms`, which closes
the utterance for transcription. This module is a pure state machine — the OpenWakeWord detector and
the audio frames are fed in by the caller, so it's fully unit-testable without audio hardware.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from jarvis.config import get_settings


@dataclass
class WakeGate:
    """Tracks whether we're actively buffering an utterance after a wake word."""

    silence_ms: int = 0
    active: bool = False
    _buffer: list[bytes] = field(default_factory=list)
    _trailing_silence_ms: int = 0

    def __post_init__(self) -> None:
        if not self.silence_ms:
            self.silence_ms = get_settings().wake_silence_ms

    def wake(self) -> None:
        """A wake word was detected — start buffering this utterance."""
        self.active = True
        self._buffer = []
        self._trailing_silence_ms = 0

    def feed(self, frame: bytes, *, is_speech: bool, frame_ms: int) -> bool:
        """Feed one audio frame. Returns True when the utterance is complete (silence elapsed)."""
        if not self.active:
            return False  # pre-wake: nothing is buffered (the privacy guarantee)
        self._buffer.append(frame)
        self._trailing_silence_ms = 0 if is_speech else self._trailing_silence_ms + frame_ms
        if self._trailing_silence_ms >= self.silence_ms and any(self._buffer):
            self.active = False
            return True
        return False

    def take(self) -> bytes:
        """Return the buffered utterance and reset."""
        audio = b"".join(self._buffer)
        self._buffer = []
        self._trailing_silence_ms = 0
        return audio
