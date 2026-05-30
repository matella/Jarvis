"""FastAPI gateway — `/ws` chat + presence, REST reads, `/health`. Transport only.

Chat in over the WebSocket → a streamed `TurnResult` + presence transitions out (for the orb). REST
endpoints are thin reads over existing repositories. Auth is a bearer token resolving to an actor
that flows into the audit log. No capability is reachable except through the conversation agent and
the existing M4 gate. Local homelab only — never expose this.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect

import jarvis.connectors  # noqa: F401 — registers connector act-Tools (mail.send, ha.set_state)
from jarvis import db
from jarvis.agents import conversation as convo
from jarvis.conversation.store import start_conversation
from jarvis.gateway import presence
from jarvis.gateway.auth import AuthError, Principal, authenticate


def _principal(authorization: str | None = Header(default=None)) -> Principal:
    try:
        return authenticate(authorization)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def _require(principal: Principal, scope: str) -> None:
    if not principal.has(scope):
        raise HTTPException(status_code=403, detail=f"missing scope: {scope}")


def create_app() -> FastAPI:
    from jarvis.plugins.loader import load_plugins

    load_plugins()  # register external tool plugins (no-op if PLUGINS_DIR unset)
    app = FastAPI(title="Jarvis Gateway", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, Any]:
        from jarvis.ops.health import health as health_snapshot

        return health_snapshot()

    @app.get("/api/events")
    def events(n: int = 20, principal: Principal = Depends(_principal)) -> list[dict]:
        _require(principal, "read")
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT id, occurred_at, type, severity, entity_ref, correlation_id "
                "FROM events ORDER BY id DESC LIMIT %s",
                (min(n, 200),),
            ).fetchall()
        return [dict(r) for r in rows]

    @app.get("/api/state")
    def state(kind: str | None = None, principal: Principal = Depends(_principal)) -> list[dict]:
        _require(principal, "read")
        sql = "SELECT entity, kind, status, attrs, updated_at FROM state"
        params: tuple = ()
        if kind:
            sql += " WHERE kind = %s"
            params = (kind,)
        sql += " ORDER BY entity"
        with db.connect() as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    @app.get("/api/incidents")
    def incidents(n: int = 20, principal: Principal = Depends(_principal)) -> list[dict]:
        _require(principal, "read")
        from jarvis.incidents.repository import list_incidents

        with db.connect() as conn:
            return [i.model_dump(mode="json") for i in list_incidents(conn, min(n, 100))]

    @app.get("/api/intents")
    def intents(n: int = 20, principal: Principal = Depends(_principal)) -> list[dict]:
        _require(principal, "read")
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT intent_id, type, status, requested_by, created_at, correlation_id "
                "FROM intents ORDER BY created_at DESC LIMIT %s",
                (min(n, 200),),
            ).fetchall()
        return [dict(r) for r in rows]

    @app.get("/api/metrics")
    def metrics(n: int = 50, principal: Principal = Depends(_principal)) -> list[dict]:
        _require(principal, "read")
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT entity, kind, sample, ts FROM metrics ORDER BY ts DESC LIMIT %s",
                (min(n, 500),),
            ).fetchall()
        return [dict(r) for r in rows]

    @app.get("/api/topology")
    def topology(principal: Principal = Depends(_principal)) -> dict[str, Any]:
        """Service-dependency graph: distinct nodes + typed edges."""
        _require(principal, "read")
        from jarvis.ingest.topology import all_edges

        with db.connect() as conn:
            edges = all_edges(conn)
        nodes = sorted({e[0] for e in edges} | {e[1] for e in edges})
        return {
            "nodes": nodes,
            "edges": [{"src": s, "dst": d, "relation": r} for s, d, r in edges],
        }

    @app.get("/api/intent/{intent_id}")
    def intent_detail(
        intent_id: str, principal: Principal = Depends(_principal)
    ) -> dict[str, Any]:
        """Full decision record: the intent, its executions, the causal trace, and its context."""
        _require(principal, "read")
        from jarvis.core.context_store import get_context
        from jarvis.intents.repository import get_executions_for_intent, get_intent

        with db.connect() as conn:
            intent = get_intent(conn, intent_id)
            if intent is None:
                raise HTTPException(status_code=404, detail="no such intent")
            executions = get_executions_for_intent(conn, intent_id)
            trace = _trace_rows(conn, intent.correlation_id)
            ctx = get_context(conn, intent.context_ref) if intent.context_ref else None
        return {
            "intent": intent.model_dump(mode="json"),
            "executions": [e.model_dump(mode="json") for e in executions],
            "trace": trace,
            "context": ({"prompt": ctx.prompt, "model": ctx.model} if ctx else None),
        }

    @app.post("/api/intent/{intent_id}/{decision}")
    def intent_decide(
        intent_id: str, decision: str, principal: Principal = Depends(_principal)
    ) -> dict[str, Any]:
        """Approve+execute or reject an intent from the approvals queue (gated + audited)."""
        _require(principal, "chat")
        from jarvis.audit.log import record
        from jarvis.intents import service

        if decision not in ("approve", "reject"):
            raise HTTPException(status_code=400, detail="decision must be approve|reject")
        actor = f"user:{principal.actor}"
        with db.connect(autocommit=True) as conn:
            try:
                if decision == "reject":
                    service.reject(conn, intent_id)
                    record(conn, actor=actor, action="intent.reject", target=intent_id)
                    return {"status": "rejected"}
                service.approve(conn, intent_id)
                record(conn, actor=actor, action="intent.approve", target=intent_id)
                execution = service.execute(conn, intent_id)
                record(conn, actor=actor, action="intent.execute", target=intent_id,
                       outcome=execution.outcome.value)
                return {"status": "executed", "outcome": execution.outcome.value}
            except service.IntentNotFound as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except (service.ApprovalRequired, service.ModeBlocked) as exc:
                return {"status": "gated", "detail": str(exc)}

    @app.get("/api/memory")
    def memory(
        kind: str | None = None, n: int = 30, principal: Principal = Depends(_principal)
    ) -> list[dict]:
        _require(principal, "read")
        from jarvis.memory.governance import list_memories

        with db.connect() as conn:
            return [dict(r) for r in list_memories(conn, kind=kind, limit=min(n, 200))]

    @app.post("/feedback")
    def feedback(
        body: dict[str, Any], principal: Principal = Depends(_principal)
    ) -> dict[str, Any]:
        """Record an operator 👍/👎 on a proposal/incident (adaptive-attention signal)."""
        _require(principal, "chat")
        from jarvis import feedback as fb

        try:
            with db.connect(autocommit=True) as conn:
                fb.record(
                    conn, target_type=str(body.get("target_type", "")),
                    target_id=str(body.get("target_id", "")),
                    rating=int(body.get("rating", 0)), actor=principal.actor,
                    note=body.get("note"),
                )
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"recorded": True}

    @app.post("/inbound/{source}")
    async def inbound(source: str, request: Request) -> dict[str, Any]:
        """Signed push from GitHub/Grafana/etc → a verified, sanitized event on the spine."""
        import json

        from jarvis.events.stream import emit_event
        from jarvis.gateway import webhooks

        body = await request.body()
        try:
            webhooks.verify(source, body, dict(request.headers))
        except webhooks.WebhookUnverified as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        try:
            payload = json.loads(body or b"{}")
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="invalid JSON") from exc
        event = webhooks.to_event(source, payload if isinstance(payload, dict) else {})
        emit_event(event)
        return {"accepted": True, "event_type": event.type, "event_id": event.id}

    @app.websocket("/ws")
    async def ws(socket: WebSocket) -> None:
        await _serve_ws(socket)

    return app


def _trace_rows(conn: Any, correlation_id: str) -> list[dict]:
    """The full causal chain (events + intents + executions) for a correlation id, id-sorted."""
    specs = (
        ("event", "events", "id", "type", "severity"),
        ("intent", "intents", "intent_id", "type", "status"),
        ("execution", "executions", "exec_id", "outcome", "failure_class"),
    )
    rows: list[dict] = []
    for kind, table, id_col, type_col, detail_col in specs:
        sql = (
            f"SELECT {id_col} AS id, {type_col} AS type, {detail_col} AS detail, causation_id "
            f"FROM {table} WHERE correlation_id = %s"
        )
        for r in conn.execute(sql, (correlation_id,)).fetchall():
            rows.append({"record_kind": kind, "id": r["id"], "type": str(r["type"]),
                         "detail": str(r["detail"]) if r["detail"] is not None else "",
                         "causation_id": r["causation_id"]})
    rows.sort(key=lambda r: r["id"])  # ULID ids sort chronologically
    return rows


async def _send_presence(socket: WebSocket, state: str) -> None:
    await socket.send_json({"kind": "presence", "state": state})


async def _serve_ws(socket: WebSocket) -> None:
    # Auth from the Authorization header or a `token` query param (browsers can't set WS headers).
    auth_header = socket.headers.get("authorization")
    if auth_header is None and (qtok := socket.query_params.get("token")):
        auth_header = f"Bearer {qtok}"
    try:
        principal = authenticate(auth_header)
    except AuthError:
        await socket.close(code=4401)
        return
    if not principal.has("chat"):
        await socket.close(code=4403)
        return

    await socket.accept()
    with db.connect(autocommit=True) as conn:
        session = start_conversation(conn, actor=principal.actor)
        session.scopes = principal.scopes
        await socket.send_json({"kind": "ready", "conversation_id": session.conversation_id})
        await _send_presence(socket, presence.baseline_presence(conn))

    try:
        while True:
            msg = await socket.receive_json()
            # Voice transport: audio in → STT → the SAME conversation path; TTS audio back out.
            if (msg or {}).get("kind") == "audio":
                utterance = await _transcribe(socket, msg.get("wav", ""))
                if not utterance:
                    continue
            else:
                utterance = (msg or {}).get("text", "").strip()
            if not utterance:
                continue
            await _send_presence(socket, presence.THINKING)
            # respond() is synchronous (DB + one inference); run it and stream the result.
            with db.connect(autocommit=True) as conn:
                result = convo.respond(conn, session, utterance)
                await socket.send_json({"kind": "turn", "result": result.model_dump(mode="json")})
                await _send_presence(socket, presence.SPEAKING)
                await _speak(socket, result.message)
                await _send_presence(socket, presence.baseline_presence(conn))
    except WebSocketDisconnect:
        return


async def _transcribe(socket: WebSocket, wav_b64: str) -> str:
    """Decode + STT an inbound audio message; echo the transcript so the UI can show it."""
    import base64

    from jarvis.voice import stt

    await _send_presence(socket, presence.LISTENING)
    try:
        text = stt.transcribe(base64.b64decode(wav_b64))
    except Exception as exc:  # noqa: BLE001 — STT unavailable/failed degrades gracefully
        await socket.send_json({"kind": "stt_error", "detail": str(exc)})
        return ""
    await socket.send_json({"kind": "transcript", "text": text})
    return text.strip()


async def _speak(socket: WebSocket, text: str) -> None:
    """Synthesize the reply to audio and stream it (the orb's AnalyserNode reacts to it)."""
    import base64

    from jarvis.voice import tts

    if not tts.available() or not text:
        return
    try:
        wav = tts.synthesize(text)
    except Exception:  # noqa: BLE001 — TTS is best-effort; the text turn already went out
        return
    await socket.send_json({"kind": "tts", "wav": base64.b64encode(wav).decode()})


app = create_app()
