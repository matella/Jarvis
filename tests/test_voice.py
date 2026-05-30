"""10 unit: STT/TTS command + parse plumbing, and the wake-word gate (no pre-wake buffering)."""

from __future__ import annotations

from jarvis.voice import stt, tts
from jarvis.voice.wake import WakeGate


def test_stt_parse_strips_timestamps() -> None:
    raw = (
        "[00:00.000 --> 00:02.000]   what's wrong with\n"
        "[00:02.000 --> 00:03.500]   my media stack\n"
    )
    assert stt.parse_output(raw) == "what's wrong with my media stack"


def test_stt_parse_plain_lines() -> None:
    assert stt.parse_output("hello there\n\n") == "hello there"


def test_stt_command_includes_model_and_file(monkeypatch) -> None:
    class S:
        whisper_bin = "whisper-cli"
        whisper_model = "/m/ggml.bin"
    monkeypatch.setattr(stt, "get_settings", lambda: S())
    cmd = stt._build_command("/tmp/a.wav")
    assert cmd[0] == "whisper-cli" and "/m/ggml.bin" in cmd and "/tmp/a.wav" in cmd


def test_tts_command(monkeypatch) -> None:
    class S:
        piper_bin = "piper"
        piper_voice = "/v/en.onnx"
    monkeypatch.setattr(tts, "get_settings", lambda: S())
    cmd = tts._build_command("/tmp/o.wav")
    assert cmd[0] == "piper" and "/v/en.onnx" in cmd and "/tmp/o.wav" in cmd


def test_availability_reflects_config(monkeypatch) -> None:
    class Off:
        whisper_model = ""
        piper_voice = ""
    monkeypatch.setattr(stt, "get_settings", lambda: Off())
    monkeypatch.setattr(tts, "get_settings", lambda: Off())
    assert stt.available() is False and tts.available() is False


def test_wake_gate_does_not_buffer_before_wake() -> None:
    gate = WakeGate(silence_ms=300)
    # frames arriving before a wake word are ignored entirely (privacy guarantee)
    assert gate.feed(b"x", is_speech=True, frame_ms=100) is False
    assert gate.take() == b""


def test_wake_gate_buffers_then_completes_on_silence() -> None:
    gate = WakeGate(silence_ms=300)
    gate.wake()
    assert gate.feed(b"aa", is_speech=True, frame_ms=100) is False  # speech
    assert gate.feed(b"bb", is_speech=False, frame_ms=100) is False  # 100ms silence
    done = gate.feed(b"cc", is_speech=False, frame_ms=200)  # 300ms total silence → complete
    assert done is True
    assert gate.active is False
    assert gate.take() == b"aabbcc"
