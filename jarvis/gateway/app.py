"""FastAPI gateway — `/ws` chat + presence, REST reads, `/health`. Transport only.

Chat in over the WebSocket → a streamed `TurnResult` + presence transitions out (for the orb). REST
endpoints are thin reads over existing repositories. Auth is a bearer token resolving to an actor
that flows into the audit log. No capability is reachable except through the conversation agent and
the existing M4 gate. Local homelab only — never expose this.
"""

from __future__ import annotations

from typing import Any

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)

import jarvis.connectors  # noqa: F401 — registers connector act-Tools (mail.send, ha.set_state)
import jarvis.modules.builtin_tools  # noqa: F401 — registers personal-OS module tools (task.*, …)
from jarvis import db
from jarvis.agents import conversation as convo
from jarvis.conversation.store import history_for_display, resume_or_start
from jarvis.gateway import presence, sessions
from jarvis.gateway.auth import AuthError, Principal
from jarvis.gateway.deps import bearer_token as _bearer_token
from jarvis.gateway.deps import principal as _principal
from jarvis.gateway.deps import require as _require


def create_app() -> FastAPI:
    from jarvis.gateway.modules_api import router as modules_router
    from jarvis.plugins.loader import load_plugins

    load_plugins()  # register external tool plugins (no-op if PLUGINS_DIR unset)
    app = FastAPI(title="Jarvis Gateway", version="0.1.0")

    # CORS so the native (Capacitor) app can call the REST API from its capacitor://localhost
    # origin. Token auth still gates every protected route; this only permits the browser/webview
    # to make the request. (WebSockets don't use CORS; /ws auth is via the token query param.)
    from fastapi.middleware.cors import CORSMiddleware

    from jarvis.config import get_settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().gateway_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(modules_router)  # personal-OS module REST (tasks/notes/docs/… + reads)

    @app.get("/health")
    def health() -> dict[str, Any]:
        from jarvis.ops.health import health as health_snapshot

        return health_snapshot()

    @app.post("/api/login")
    def login(request: Request, response: Response, body: dict[str, Any]) -> dict[str, Any]:
        # Unauthenticated by design: the passphrase IS the credential. Single operator,
        # Tailscale-only. The minted token is set as an HttpOnly cookie (browser) AND returned in
        # the body so the cross-origin native app can store it and send it as a bearer.
        from jarvis.security.secrets import get_provider

        s = get_settings()
        stored = get_provider().get("APP_PASSPHRASE_HASH")
        if not sessions.verify_passphrase(str(body.get("passphrase", "")), stored):
            raise HTTPException(status_code=401, detail="invalid passphrase")
        with db.connect() as conn:
            token = sessions.mint_session(
                conn, ttl_days=s.app_session_ttl_days,
                user_agent=request.headers.get("user-agent"),
            )
        response.set_cookie(
            s.app_session_cookie, token, httponly=True, samesite="lax",
            secure=request.url.scheme == "https", max_age=s.app_session_ttl_days * 86400, path="/",
        )
        return {"ok": True, "token": token}

    @app.post("/api/logout")
    def logout(
        request: Request, response: Response, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        cookie_name = get_settings().app_session_cookie
        token = request.cookies.get(cookie_name) or _bearer_token(authorization)
        if token:
            with db.connect() as conn:
                sessions.revoke_session(conn, token)
        response.delete_cookie(cookie_name, path="/")
        return {"ok": True}

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

    @app.get("/api/torrents")
    def torrents(principal: Principal = Depends(_principal)) -> dict[str, Any]:
        """Live qBittorrent download snapshot (read-only)."""
        _require(principal, "read")
        from jarvis.connectors.qbittorrent import fetch_snapshot

        return fetch_snapshot()

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
    # Same resolver as REST: a session token (the app passes ?token=<session>) → operator; else if a
    # passphrase is configured, reject; else open-dev. Keeps chat gated whenever the app is.
    from jarvis.gateway.deps import resolve_principal

    auth_header = socket.headers.get("authorization")
    qtok = socket.query_params.get("token")
    token = qtok or _bearer_token(auth_header)
    try:
        principal = resolve_principal(token, auth_header)
    except AuthError:
        await socket.close(code=4401)
        return
    if not principal.has("chat"):
        await socket.close(code=4403)
        return

    await socket.accept()
    # The client passes its last conversation id (?cid=) so a refresh resumes the same thread
    # instead of starting a blank one. Ownership is checked server-side (resume_or_start).
    prior_cid = socket.query_params.get("cid") or None
    with db.connect(autocommit=True) as conn:
        session = resume_or_start(conn, actor=principal.actor, conversation_id=prior_cid)
        session.scopes = principal.scopes
        await socket.send_json({"kind": "ready", "conversation_id": session.conversation_id})
        history = history_for_display(conn, session.conversation_id)
        if history:
            await socket.send_json({
                "kind": "history",
                "messages": [
                    {"role": m["role"], "content": m["content"], "artifacts": m["artifacts"]}
                    for m in history
                ],
            })
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
            # respond() is synchronous (DB + one inference); run it and stream the result. A
            # failure here (model unreachable, DB blip) must degrade to a spoken apology, NOT
            # crash the socket — the deterministic spine keeps running regardless.
            try:
                with db.connect(autocommit=True) as conn:
                    result = convo.respond(conn, session, utterance)
                    await socket.send_json(
                        {"kind": "turn", "result": result.model_dump(mode="json")}
                    )
                    await _send_presence(socket, presence.SPEAKING)
                    await _speak(socket, result.message)
                    await _send_presence(socket, presence.baseline_presence(conn))
            except WebSocketDisconnect:
                raise
            except Exception as exc:  # noqa: BLE001 — degrade, don't drop the connection
                await socket.send_json({
                    "kind": "turn",
                    "result": convo.TurnResult(
                        route=convo.TurnRoute.answer,
                        message=f"I hit a problem handling that ({type(exc).__name__}). "
                                "The system is still running — try again in a moment.",
                    ).model_dump(mode="json"),
                })
                await _send_presence(socket, presence.IDLE)
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
