from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def fall():
    return {"event_id": str(uuid4()), "camera_id": "camera-1", "zone_id": "Zone 1",
            "timestamp": datetime.now(timezone.utc).isoformat(), "event_type": "fall",
            "pose_confidence": 0.9, "metadata": {"trigger": "auto"}}


def assessment(outcome, seconds_down=10.0):
    return {"outcome": outcome, "seconds_down": seconds_down, "motion": 0.004,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "camera_id": "camera-1", "zone_id": "Zone 1"}


def make_client(tmp_path):
    settings = Settings(sqlite_path=str(tmp_path / "incidents.sqlite3"),
                        api_key="test-key", alert_provider="none")
    return TestClient(create_app(settings), headers={"X-API-Key": "test-key"})


def test_assessment_records_outcome_without_external_alerts(tmp_path):
    with make_client(tmp_path) as client:
        incident_id = client.post("/api/v1/telemetry", json=fall()).json()["incident"]["incident_id"]
        result = client.post(f"/api/v1/incidents/{incident_id}/assessment",
                             json=assessment("unresponsive"))
        assert result.status_code == 200
        incident = result.json()["incident"]
        assert incident["metadata"]["assessment"] == "unresponsive"
        assert incident["metadata"]["unresponsive_alert"] == "not_configured"
        assert incident["alert_results"] == []


def test_repeating_assessment_is_deduplicated(tmp_path):
    with make_client(tmp_path) as client:
        incident_id = client.post("/api/v1/telemetry", json=fall()).json()["incident"]["incident_id"]
        body = assessment("moving")
        client.post(f"/api/v1/incidents/{incident_id}/assessment", json=body)
        again = client.post(f"/api/v1/incidents/{incident_id}/assessment", json=body)
        assert again.json()["status"] == "duplicate"
