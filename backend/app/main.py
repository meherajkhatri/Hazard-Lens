import asyncio
import hmac
import json
import sqlite3
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID

import httpx
import anyio
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime, ValidationError

from app.config import Settings
from app.realtime import EventHub
from app.schemas import CoachRequest, EmailAlert, FallAssessment, IncidentAlert, IncidentUpdate, SMSAlert, TelemetryEvent
from app.services.alert_dispatcher import AlertDispatcher
from app.services.coach import SafetyCoach
from app.services.telemetry import TelemetryService
from app.storage import SQLiteStore, SupabaseStore


def create_app(settings=None, *, transport=None, smtp_factory=None):
    settings = settings or Settings.from_env()
    settings.validate()

    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(timeout=10, transport=transport) as client:
            store = SQLiteStore(settings.sqlite_path) if settings.storage == "sqlite" else SupabaseStore(settings, client)
            hub = EventHub()
            dispatcher = AlertDispatcher(settings, client, smtp_factory=smtp_factory)
            app.state.store = store
            app.state.hub = hub
            app.state.dispatcher = dispatcher
            app.state.telemetry = TelemetryService(settings, store, dispatcher, hub)
            app.state.coach = SafetyCoach(settings, client, store)
            yield

    app = FastAPI(title="Call-Help Safety API", version="0.2.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH"], allow_headers=["Content-Type", "X-API-Key"])

    async def authenticate(x_api_key: str = Header(default="")):
        if settings.api_key and not hmac.compare_digest(x_api_key.encode(), settings.api_key.encode()):
            raise HTTPException(401, "Invalid API key")

    async def storage_error(request, exc):
        return JSONResponse(status_code=503, content={"detail": "Incident storage unavailable"})

    app.add_exception_handler(httpx.HTTPError, storage_error)
    app.add_exception_handler(sqlite3.Error, storage_error)
    router = APIRouter(prefix="/api/v1", dependencies=[Depends(authenticate)])

    @app.get("/health")
    async def health():
        return {"status": "ok", "storage": settings.storage, "sms_mode": settings.sms_mode,
            "alert_provider": settings.alert_provider,
            "coach_mode": "gemini" if settings.gemini_key else "local_summary"}

    @router.get("/ready")
    async def ready():
        await app.state.store.list(limit=1)
        return {"status": "ready"}

    @router.post("/telemetry")
    async def ingest(event: TelemetryEvent):
        return await app.state.telemetry.ingest(event)

    @router.get("/incidents", response_model=list[IncidentAlert])
    async def incidents(zone_id: str | None = None,
        status: Literal["active", "acknowledged", "resolved"] | None = None,
        since: AwareDatetime | None = None, until: AwareDatetime | None = None,
        limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
        if since and until and since > until:
            raise HTTPException(422, "since must be before until")
        return await app.state.store.list(zone_id=zone_id, status=status, since=since, until=until, limit=limit, offset=offset)

    @router.get("/incidents/{incident_id}", response_model=IncidentAlert)
    async def incident(incident_id: UUID):
        result = await app.state.store.get(incident_id)
        if not result:
            raise HTTPException(404, "Incident not found")
        return result

    @router.patch("/incidents/{incident_id}", response_model=IncidentAlert)
    async def update_incident(incident_id: UUID, update: IncidentUpdate):
        async with app.state.telemetry.lock:
            current = await incident(incident_id)
            if current.status == "resolved" and update.status != "resolved":
                raise HTTPException(409, "Resolved incidents cannot be reopened")
            result = await app.state.store.update(incident_id, update.model_dump())
        await app.state.hub.publish({"type": "incident.updated", "incident": result.model_dump(mode="json")})
        return result

    @router.post("/incidents/{incident_id}/assessment")
    async def assess_incident(incident_id: UUID, assessment: FallAssessment):
        return await app.state.telemetry.assess(incident_id, assessment)

    @router.post("/alerts/sms")
    async def sms(alert: SMSAlert):
        if alert.recipient not in settings.sms_recipients:
            raise HTTPException(403, "Recipient is not in SMS_RECIPIENTS")
        return await app.state.dispatcher.send_sms_alert(alert)

    @router.post("/alerts/email")
    async def email(alert: EmailAlert):
        if settings.alert_provider != "brevo_email":
            raise HTTPException(409, "Brevo email alerts are not enabled")
        if alert.recipient not in settings.brevo_recipients:
            raise HTTPException(403, "Recipient is not in BREVO_RECIPIENTS")
        return await app.state.dispatcher.send_email_alert(alert)

    @router.post("/coach/chat")
    async def coach(request: CoachRequest):
        if request.since and request.until and request.since > request.until:
            raise HTTPException(422, "since must be before until")
        return await app.state.coach.answer(request)

    async def connect(socket):
        origin = socket.headers.get("origin")
        if origin and origin not in settings.cors_origins:
            await socket.close(code=1008)
            return False
        await socket.accept()
        if settings.api_key:
            try:
                raw = await asyncio.wait_for(socket.receive_text(), timeout=5)
                message = json.loads(raw) if len(raw) <= 4096 else {}
                supplied = message.get("api_key", "") if isinstance(message, dict) else ""
                if not isinstance(supplied, str) or not hmac.compare_digest(supplied.encode(), settings.api_key.encode()):
                    await socket.close(code=1008)
                    return False
            except (ValueError, TimeoutError, WebSocketDisconnect):
                await socket.close(code=1008)
                return False
        return True

    @app.websocket("/ws/incidents")
    async def live_incidents(socket: WebSocket):
        if not await connect(socket):
            return
        queue = app.state.hub.subscribe(socket)
        async def send_events():
            while True:
                await socket.send_json(await queue.get())

        async def receive():
            while True:
                await socket.receive_text()

        try:
            await socket.send_json({"type": "connected"})
            # Keep both workers inside the connection's cancellation scope.
            # Raw asyncio tasks can outlive an ASGI disconnect/shutdown scope.
            async with anyio.create_task_group() as group:
                async def run_worker(worker):
                    try:
                        await worker()
                    except (WebSocketDisconnect, RuntimeError):
                        pass
                    finally:
                        group.cancel_scope.cancel()
                group.start_soon(run_worker, send_events)
                group.start_soon(run_worker, receive)
        finally:
            app.state.hub.unsubscribe(socket)

    @app.websocket("/ws/telemetry")
    async def live_telemetry(socket: WebSocket):
        if not await connect(socket):
            return
        await socket.send_json({"type": "connected"})
        try:
            while True:
                raw = await socket.receive_text()
                if len(raw) > 65536:
                    await socket.close(code=1009)
                    return
                try:
                    event = TelemetryEvent.model_validate_json(raw)
                    result = await app.state.telemetry.ingest(event)
                    await socket.send_json({"type": "telemetry.result", **result})
                except ValidationError:
                    await socket.send_json({"type": "error", "status": 422, "detail": "Invalid telemetry; see /docs for schema"})
                except HTTPException as exc:
                    await socket.send_json({"type": "error", "status": exc.status_code, "detail": exc.detail})
                except (httpx.HTTPError, sqlite3.Error):
                    await socket.send_json({"type": "error", "status": 503, "detail": "Incident storage unavailable"})
        except WebSocketDisconnect:
            pass

    app.include_router(router)
    return app


app = create_app()
