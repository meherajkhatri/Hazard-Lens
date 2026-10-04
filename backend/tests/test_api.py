from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.seed import seed


def settings(tmp_path):
    return Settings(sqlite_path=str(tmp_path / "incidents.sqlite3"),
                    api_key="test-key", alert_provider="none")


def event(**updates):
    return {"event_id": str(uuid4()), "camera_id": "camera-1", "zone_id": "Zone 1",
            "timestamp": datetime.now(timezone.utc).isoformat(), "pose_event": "fall",
            "confidence_score": 0.96, **updates}


def test_persist_dedupe_and_conflict(tmp_path):
    config = settings(tmp_path)
    payload = event()
    with TestClient(create_app(config), headers={"X-API-Key": "test-key"}) as client:
        first = client.post("/api/v1/telemetry", json=payload).json()
        duplicate = client.post("/api/v1/telemetry", json=payload).json()
        assert first["status"] == "received"
        assert duplicate["status"] == "duplicate"
        assert first["incident"]["alert_status"] == "not_configured"
        assert client.post("/api/v1/telemetry", json={**payload, "zone_id": "Zone 2"}).status_code == 409


def test_cooldown_and_threshold(tmp_path):
    config = settings(tmp_path)
    with TestClient(create_app(config), headers={"X-API-Key": "test-key"}) as client:
        first = client.post("/api/v1/telemetry", json=event()).json()
        second = client.post("/api/v1/telemetry", json=event()).json()
        assert first["incident"]["alert_status"] == "not_configured"
        assert second["incident"]["alert_status"] == "not_configured"
        assert client.post("/api/v1/telemetry", json=event(confidence_score=0.2)).json()["status"] == "ignored"


def test_automatic_alert_requires_confidence_above_90_percent(tmp_path):
    class SMTP:
        def __init__(self, *args, **kwargs):
            self.sent = False
        def ehlo(self): pass
        def starttls(self, context): pass
        def login(self, login, key): pass
        def send_message(self, message): self.sent = True
        def quit(self): pass

    smtp = SMTP()
    config = Settings(sqlite_path=str(tmp_path / "incidents.sqlite3"), api_key="test-key",
                      alert_provider="brevo_email", brevo_smtp_login="login",
                      brevo_smtp_key="key", brevo_from_email="from@example.com",
                      brevo_recipients=["to@example.com"])
    with TestClient(create_app(config, smtp_factory=lambda *args, **kwargs: smtp),
                   headers={"X-API-Key": "test-key"}) as client:
        below = client.post("/api/v1/telemetry", json=event(confidence_score=0.9)).json()
        above = client.post("/api/v1/telemetry", json=event(confidence_score=0.901)).json()
        assert below["incident"]["alert_status"] == "not_configured"
        assert above["incident"]["alert_status"] == "queued"
        assert smtp.sent


def test_auth_and_removed_sms_endpoint(tmp_path):
    with TestClient(create_app(settings(tmp_path)), headers={"X-API-Key": "test-key"}) as client:
        assert client.get("/api/v1/incidents", headers={"X-API-Key": "wrong"}).status_code == 401
        assert client.post("/api/v1/alerts/sms", json={"recipient": "+15555550123", "message": "hello"}).status_code == 404


def test_seed_is_idempotent_and_alert_free(tmp_path):
    config = settings(tmp_path)
    assert __import__("asyncio").run(seed(config)) == 18
    assert __import__("asyncio").run(seed(config)) == 0
    with TestClient(create_app(config), headers={"X-API-Key": "test-key"}) as client:
        rows = client.get("/api/v1/incidents").json()
        assert len(rows) == 18
        assert all(row["alert_status"] == "not_configured" for row in rows)


def test_sqlite_migrates_legacy_sms_payload(tmp_path):
    import json
    import sqlite3
    from app.storage import SQLiteStore
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE incidents (incident_id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        db.execute("INSERT INTO incidents VALUES (?, ?)",
                   ("legacy", json.dumps({"incident_id": "legacy", "sms_status": "queued",
                   "sms_results": [], "metadata": {}})))
    SQLiteStore(path)
    with sqlite3.connect(path) as db:
        payload = json.loads(db.execute("SELECT payload FROM incidents").fetchone()[0])
    assert payload["alert_status"] == "queued"
    assert "sms_status" not in payload
