import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.config import Settings
from app.main import create_app
from app.seed import seed


@pytest.fixture
def settings(tmp_path):
    return Settings(sqlite_path=str(tmp_path / "incidents.sqlite3"), api_key="test-key",
        sms_recipients=["+15555550123"])


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings), headers={"X-API-Key": "test-key"}) as client:
        yield client


def event(**updates):
    return {"event_id": str(uuid4()), "camera_id": "camera-1", "zone_id": "Zone 1",
        "timestamp": datetime.now(timezone.utc).isoformat(), "pose_event": "fall",
        "confidence_score": 0.96, **updates}


def test_persist_dedupe_and_conflict(settings):
    payload = event()
    for index in range(2):
        with TestClient(create_app(settings), headers={"X-API-Key": "test-key"}) as client:
            result = client.post("/api/v1/telemetry", json=payload)
            assert result.status_code == 200
            assert result.json()["status"] == ["received", "duplicate"][index]
            assert result.json()["incident"]["sms_status"] == "dry_run"
            assert len(client.get("/api/v1/incidents").json()) == 1
            assert client.post("/api/v1/telemetry", json={**payload, "zone_id": "Zone 2"}).status_code == 409


def test_generated_identity_and_cooldown(client):
    payload = event()
    del payload["event_id"]
    first = client.post("/api/v1/telemetry", json=payload).json()
    assert first["incident"]["sms_status"] == "dry_run"
    assert client.post("/api/v1/telemetry", json=payload).json()["status"] == "duplicate"
    second = client.post("/api/v1/telemetry", json=event()).json()
    assert second["incident"]["sms_status"] == "cooldown"
    assert len(client.get("/api/v1/incidents").json()) == 2


@pytest.mark.parametrize("updates", [{"confidence_score": 2}, {"timestamp": "2026-10-03T12:00:00"},
    {"pose_event": "other"}, {"zone_id": " "}, {"camera_id": ""}])
def test_validation(client, updates):
    assert client.post("/api/v1/telemetry", json=event(**updates)).status_code == 422


@pytest.mark.parametrize("updates", [{"confidence_score": 0.2}, {"pose_event": "normal"}])
def test_non_incidents_not_stored(client, updates):
    assert client.post("/api/v1/telemetry", json=event(**updates)).json()["status"] == "ignored"
    assert client.get("/api/v1/incidents").json() == []


def test_auth_and_recipient_allowlist(client):
    assert client.get("/api/v1/incidents", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.post("/api/v1/alerts/sms", json={"recipient": "+15555550999", "message": "hello"}).status_code == 403
    assert client.post("/api/v1/alerts/sms", json={"recipient": "+15555550123", "message": "hello"}).json()["status"] == "dry_run"
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/incidents") as socket:
            socket.send_json({"api_key": "wrong"})
            socket.receive_json()


def test_lifecycle_filters_and_dates(client):
    payload = event(timestamp="2026-10-03T09:00:00-04:00")
    record = client.post("/api/v1/telemetry", json=payload).json()["incident"]
    path = f"/api/v1/incidents/{record['incident_id']}"
    assert client.patch(path, json={"status": "acknowledged"}).json()["status"] == "acknowledged"
    assert client.get("/api/v1/incidents", params={"status": "active"}).json() == []
    assert len(client.get("/api/v1/incidents", params={"since": "2026-10-03T12:59:00Z", "zone_id": "Zone 1"}).json()) == 1
    assert client.get("/api/v1/incidents", params={"since": "2026-10-03T13:01:00Z"}).json() == []
    assert client.patch(path, json={"status": "resolved"}).status_code == 200
    assert client.patch(path, json={"status": "acknowledged"}).status_code == 409
    assert client.get(f"/api/v1/incidents/{uuid4()}").status_code == 404
    assert client.get("/api/v1/incidents?limit=0").status_code == 422


def test_websocket_ingestion_and_broadcast(client):
    with client.websocket_connect("/ws/incidents") as dashboard:
        dashboard.send_json({"api_key": "test-key"})
        assert dashboard.receive_json()["type"] == "connected"
        with client.websocket_connect("/ws/telemetry") as camera:
            camera.send_json({"api_key": "test-key"})
            assert camera.receive_json()["type"] == "connected"
            camera.send_text("invalid")
            assert camera.receive_json()["status"] == 422
            camera.send_json(event())
            result = camera.receive_json()
            assert result["status"] == "received"
            created = dashboard.receive_json()
            assert created["type"] == "incident.created"
            assert created["incident"]["incident_id"] == result["incident"]["incident_id"]
            assert dashboard.receive_json()["incident"]["sms_status"] == "dry_run"


def test_seed_is_idempotent_no_alerts_and_coach_filters(settings):
    assert asyncio.run(seed(settings)) == 18
    assert asyncio.run(seed(settings)) == 0
    with TestClient(create_app(settings), headers={"X-API-Key": "test-key"}) as client:
        rows = client.get("/api/v1/incidents").json()
        assert len(rows) == 18
        assert all(row["sms_status"] == "not_required" for row in rows)
        response = client.post("/api/v1/coach/chat", json={"question": "Summarize risks", "zone_id": "Zone 1"}).json()
        assert response["mode"] == "local_summary"
        assert response["context_count"] == 6
        assert set(response["incident_ids"]) == {row["incident_id"] for row in rows if row["zone_id"] == "Zone 1"}


@pytest.mark.parametrize("provider_status,expected", [(201, "queued"), (400, "failed"), (504, "failed")])
def test_twilio_response_persisted(settings, provider_status, expected):
    settings.sms_mode = "twilio"
    settings.twilio_sid, settings.twilio_token, settings.twilio_from = "ACtest", "secret", "+15555550111"
    calls = []
    def handler(request):
        calls.append(request)
        assert request.url.host == "api.twilio.com"
        assert b"To=%2B15555550123" in request.content
        return httpx.Response(provider_status, json={"sid": "SMtest", "status": "queued"})
    with TestClient(create_app(settings, transport=httpx.MockTransport(handler)), headers={"X-API-Key": "test-key"}) as client:
        payload = event()
        record = client.post("/api/v1/telemetry", json=payload).json()["incident"]
        assert record["sms_status"] == expected
        client.post("/api/v1/telemetry", json=payload)
        assert len(calls) == 1


def test_twilio_timeout_not_reported_as_sent(settings):
    settings.sms_mode = "twilio"
    settings.twilio_sid, settings.twilio_token, settings.twilio_from = "ACtest", "secret", "+15555550111"
    def handler(request):
        raise httpx.ReadTimeout("timeout", request=request)
    with TestClient(create_app(settings, transport=httpx.MockTransport(handler)), headers={"X-API-Key": "test-key"}) as client:
        record = client.post("/api/v1/telemetry", json=event()).json()["incident"]
        assert record["sms_status"] == "unknown"


def test_gemini_context_and_failure(settings):
    import json
    settings.gemini_key, settings.gemini_model = "secret", "test-model"
    requests = []
    def handler(request):
        requests.append(request)
        assert request.headers["x-goog-api-key"] == "secret"
        context = json.loads(json.loads(request.content)["contents"][0]["parts"][0]["text"])
        assert len(context["incidents"]) == 1
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "One recorded fall."}]}}]})
    with TestClient(create_app(settings, transport=httpx.MockTransport(handler)), headers={"X-API-Key": "test-key"}) as client:
        client.post("/api/v1/telemetry", json=event())
        result = client.post("/api/v1/coach/chat", json={"question": "Summarize", "zone_id": "Zone 1"}).json()
        assert result["mode"] == "gemini" and result["answer"] == "One recorded fall."
    with TestClient(create_app(settings, transport=httpx.MockTransport(lambda _: httpx.Response(503))), headers={"X-API-Key": "test-key"}) as client:
        assert client.post("/api/v1/coach/chat", json={"question": "Summarize"}).status_code == 502
