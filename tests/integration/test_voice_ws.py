"""10 integration: voice in over /ws → STT → the same conversation path → turn out.

Mocks the STT binary (a recorded WAV → fixed text) so it runs offline; everything downstream is the
real gateway + conversation pipeline. Proves voice is pure transport: an audio message produces a
transcript echo and then a normal turn, with presence flipping listening→thinking.
"""

from __future__ import annotations

import base64

import psycopg
import pytest
from starlette.testclient import TestClient

from jarvis.agents import conversation as convo
from jarvis.agents.conversation import _Decision
from jarvis.gateway.app import app
from jarvis.voice import stt

pytestmark = pytest.mark.integration


def test_audio_message_transcribes_and_answers(
    db_conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(stt, "transcribe", lambda _wav: "what is degraded")
    monkeypatch.setattr(
        convo, "_decide",
        lambda *a, **k: _Decision(route="answer", message="Nothing is degraded."),
    )

    conversation_id = None
    try:
        with TestClient(app).websocket_connect("/ws") as ws:
            ready = ws.receive_json()
            conversation_id = ready["conversation_id"]
            assert ws.receive_json()["kind"] == "presence"  # baseline

            ws.send_json({"kind": "audio", "wav": base64.b64encode(b"FAKEWAV").decode()})
            assert ws.receive_json() == {"kind": "presence", "state": "listening"}
            transcript = ws.receive_json()
            assert transcript == {"kind": "transcript", "text": "what is degraded"}
            assert ws.receive_json()["state"] == "thinking"
            turn = ws.receive_json()
            assert turn["kind"] == "turn"
            assert turn["result"]["message"] == "Nothing is degraded."
            # TTS is unavailable by default → no audio frame, just presence back to baseline
            assert ws.receive_json()["state"] == "speaking"
            assert ws.receive_json()["kind"] == "presence"
    finally:
        if conversation_id:
            db_conn.execute("DELETE FROM conversations WHERE id = %s", (conversation_id,))
