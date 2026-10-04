"""Post-fall assessment endpoint, escalation texts, per-zone cooldown and the
WhatsApp channel. Twilio is mocked; nothing is sent."""

from datetime import datetime, timezone
from urllib.parse import parse_qs
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(sqlite_path=str(tmp_path / "incidents.sqlite3"), api_key="test-key",
                    sms_recipients=["+15555550123"], sms_mode="twilio", twilio_sid="ACtest",
                    twilio_token="secret", twilio_from="+15555550111")


class FakeTwilio:
    def __init__(self):
        self.sent = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.sent.append({k: v[0] for k, v in parse_qs(request.content.decode()).items()})
        return httpx.Response(201, json={"status": "queued", "sid": f"SM{len(self.sent)}"})


@pytest.fixture
def twilio():
    return FakeTwilio()


@pytest.fixture
def client(settings, twilio):
    with TestClient(create_app(settings, transport=httpx.MockTransport(twilio)),
                    headers={"X-API-Key": "test-key"}) as client:
        yield client


def fall(camera_id="zone-1-cam-1", zone_id="Zone 1"):
    return {"event_id": str(uuid4()), "camera_id": camera_id, "zone_id": zone_id,
            "timestamp": datetime.now(timezone.utc).isoformat(), "event_type": "fall",
            "pose_confidence": 0.9, "metadata": {"trigger": "auto"}}


def assessment(outcome, seconds_down=10.0):
    return {"outcome": outcome, "seconds_down": seconds_down, "motion": 0.004,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "camera_id": "zone-1-cam-1", "zone_id": "Zone 1"}


def post_fall(client):
    return client.post("/api/v1/telemetry", json=fall()).json()["incident"]["incident_id"]


def test_unresponsive_escalates_even_inside_the_cooldown(client, twilio):
    incident_id = post_fall(client)
    assert len(twilio.sent) == 1  # the original fall alert
    result = client.post(f"/api/v1/incidents/{incident_id}/assessment", json=assessment("unresponsive"))
    assert result.status_code == 200
    incident = result.json()["incident"]
    assert incident["metadata"]["assessment"] == "unresponsive"
    assert incident["metadata"]["unresponsive_sms"] == "queued"
    assert "NO MOVEMENT" in incident["description"]
    assert len(twilio.sent) == 2 and "URGENT" in twilio.sent[1]["Body"] and "NO MOVEMENT" in twilio.sent[1]["Body"]
    assert len(incident["sms_results"]) == 2  # original + escalation kept


def test_same_outcome_twice_sends_nothing_more(client, twilio):
    incident_id = post_fall(client)
    client.post(f"/api/v1/incidents/{incident_id}/assessment", json=assessment("unresponsive"))
    again = client.post(f"/api/v1/incidents/{incident_id}/assessment", json=assessment("unresponsive"))
    assert again.json()["status"] == "duplicate" and len(twilio.sent) == 2


def test_recovered_after_unresponsive_sends_an_update(client, twilio):
    incident_id = post_fall(client)
    client.post(f"/api/v1/incidents/{incident_id}/assessment", json=assessment("unresponsive"))
    result = client.post(f"/api/v1/incidents/{incident_id}/assessment", json=assessment("recovered", 25))
    assert result.json()["incident"]["metadata"]["assessment"] == "recovered"
    assert len(twilio.sent) == 3 and "got back up after 25s" in twilio.sent[2]["Body"]


def test_quick_recovery_or_moving_is_recorded_without_a_text(client, twilio):
    for outcome in ("recovered", "moving"):
        incident_id = post_fall(client) if outcome == "recovered" else post_fall(client)
        result = client.post(f"/api/v1/incidents/{incident_id}/assessment", json=assessment(outcome, 3))
        assert result.json()["incident"]["metadata"]["assessment"] == outcome
    assert len(twilio.sent) == 1  # only the first fall's alert; the second fall was in cooldown


def test_assessment_is_broadcast_to_the_dashboard(client):
    incident_id = post_fall(client)
    with client.websocket_connect("/ws/incidents") as socket:
        socket.send_text('{"api_key": "test-key"}')
        assert socket.receive_json()["type"] == "connected"
        client.post(f"/api/v1/incidents/{incident_id}/assessment", json=assessment("moving"))
        update = socket.receive_json()
        assert update["type"] == "incident.updated" and update["incident"]["metadata"]["assessment"] == "moving"


def test_unknown_incident_and_bad_body_are_rejected(client):
    assert client.post(f"/api/v1/incidents/{uuid4()}/assessment", json=assessment("moving")).status_code == 404
    incident_id = post_fall(client)
    assert client.post(f"/api/v1/incidents/{incident_id}/assessment",
                       json={**assessment("moving"), "outcome": "fine"}).status_code == 422
    assert client.post(f"/api/v1/incidents/{incident_id}/assessment",
                       json={**assessment("moving"), "extra": 1}).status_code == 422


def test_assessment_requires_the_api_key(settings, twilio):
    with TestClient(create_app(settings, transport=httpx.MockTransport(twilio))) as client:
        assert client.post(f"/api/v1/incidents/{uuid4()}/assessment", json=assessment("moving")).status_code == 401


def test_two_cameras_on_one_zone_send_one_text(client, twilio):
    first = client.post("/api/v1/telemetry", json=fall(camera_id="zone-1-cam-1")).json()
    second = client.post("/api/v1/telemetry", json=fall(camera_id="zone-1-cam-2")).json()
    assert first["incident"]["sms_status"] == "queued"
    assert second["incident"]["sms_status"] == "cooldown"
    assert len(twilio.sent) == 1
    other_zone = client.post("/api/v1/telemetry", json=fall(camera_id="corridor-cam-1", zone_id="Forklift Corridor")).json()
    assert other_zone["incident"]["sms_status"] == "queued" and len(twilio.sent) == 2


def test_whatsapp_channel_prefixes_numbers(settings, twilio):
    settings.sms_channel = "whatsapp"
    with TestClient(create_app(settings, transport=httpx.MockTransport(twilio)),
                    headers={"X-API-Key": "test-key"}) as client:
        client.post("/api/v1/telemetry", json=fall())
    assert twilio.sent[0]["From"] == "whatsapp:+15555550111"
    assert twilio.sent[0]["To"] == "whatsapp:+15555550123"


def test_invalid_channel_is_rejected(settings):
    settings.sms_channel = "pager"
    with pytest.raises(ValueError, match="SMS_CHANNEL"):
        settings.validate()
