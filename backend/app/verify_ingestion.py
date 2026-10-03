"""Exercise FastAPI routes against configured storage; force SMS dry-run for this probe."""
from dataclasses import replace
from datetime import datetime, timezone
import json
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def verify(settings):
    # No recipient is contacted, even if the user's normal configuration enables Twilio.
    settings = replace(settings, sms_mode="dry_run", sms_recipients=["+15555550123"],
        gemini_key="", api_key=settings.api_key or "isolated-verification-key")
    probe_id = str(uuid4())
    result = {"status": "failed", "storage": settings.storage, "sms_mode": "dry_run",
        "probe_id": probe_id, "checks": [], "transport": "in_process_fastapi_with_real_storage"}
    def check(condition, name):
        if not condition:
            raise ValueError(name)
        result["checks"].append(name)
    try:
        with TestClient(create_app(settings), headers={"X-API-Key": settings.api_key}) as client:
            check(client.get("/api/v1/ready").status_code == 200, "storage_ready")
            payload = {"event_id": probe_id, "camera_id": f"verification-{probe_id}",
                "zone_id": "API Verification", "timestamp": datetime.now(timezone.utc).isoformat(),
                "pose_event": "fall", "confidence_score": .96,
                "metadata": {"simulated": True, "api_probe": True}}
            response = client.post("/api/v1/telemetry", json=payload)
            check(response.status_code == 200 and response.json().get("status") == "received", "fall_ingestion")
            check(response.json()["incident"]["sms_status"] == "dry_run", "sms_dry_run_recorded")
            check(client.post("/api/v1/telemetry", json=payload).json().get("status") == "duplicate", "retry_deduplicated")
            check(client.post("/api/v1/telemetry", json={**payload, "zone_id": "Conflict"}).status_code == 409,
                "conflicting_retry_rejected")
            path = f"/api/v1/incidents/{probe_id}"
            stored = client.get(path)
            check(stored.status_code == 200 and stored.json()["zone_id"] == "API Verification", "persisted_readback")
            check(client.patch(path, json={"status": "acknowledged"}).json().get("status") == "acknowledged", "acknowledged")
            check(client.patch(path, json={"status": "resolved"}).json().get("status") == "resolved", "resolved")
        # Recreate app/client to ensure state came from persistent storage.
        with TestClient(create_app(settings), headers={"X-API-Key": settings.api_key}) as client:
            check(client.get(path).json().get("status") == "resolved", "persisted_after_restart")
        return {**result, "status": "passed"}
    except (ValueError, KeyError, TypeError):
        return {**result, "error": "verification_failed_after_last_recorded_check"}


if __name__ == "__main__":
    settings = Settings.from_env()
    if settings.storage != "supabase" or not settings.supabase_key:
        print(json.dumps({"status": "blocked", "error": "Configure Supabase first"}))
        raise SystemExit(1)
    result = verify(settings)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "passed" else 1)
