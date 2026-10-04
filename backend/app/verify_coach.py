"""Live Coach acceptance probe: one labeled incident, two Gemini requests, never SMS."""
from dataclasses import replace
from datetime import datetime, timezone
import json
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def verify(settings, *, transport=None):
    if not (settings.gemini_key and settings.gemini_model and settings.api_key):
        return {"status": "blocked", "error": "Configure GEMINI_API_KEY, GEMINI_MODEL, and API_KEY"}
    settings = replace(settings, sms_mode="dry_run", sms_recipients=[])
    probe_id = str(uuid4())
    zone = "Coach Verification " + probe_id
    result = {"status": "failed", "probe_id": probe_id, "checks": [], "answers": [],
        "storage": settings.storage, "sms_mode": "dry_run"}
    def check(condition, name):
        if not condition:
            raise ValueError(name)
        result["checks"].append(name)
    try:
        with TestClient(create_app(settings, transport=transport), headers={"X-API-Key": settings.api_key}) as client:
            event = {"event_id": probe_id, "camera_id": "coach-probe", "zone_id": zone,
                "timestamp": datetime.now(timezone.utc).isoformat(), "pose_event": "fall",
                "confidence_score": .9, "metadata": {"simulated": True, "coach_probe": True}}
            response = client.post("/api/v1/telemetry", json=event)
            check(response.status_code == 200, "probe_persisted")
            # Resolve before calling AI so provider failure never leaves an active test incident.
            check(client.patch(f"/api/v1/incidents/{probe_id}", json={"status": "resolved"}).status_code == 200,
                "probe_resolved")
            response = client.post("/api/v1/coach/chat", json={"zone_id": zone,
                "question": "Summarize the available records in one sentence, label simulated data, and cite the full incident ID. Do not infer a cause."})
            check(response.status_code == 200, "gemini_responded")
            data = response.json()
            check(data.get("mode") == "gemini" and data.get("incident_ids") == [probe_id], "live_mode_and_source_match")
            check(probe_id in data.get("answer", ""), "answer_cites_incident")
            result["answers"].append(data["answer"])
            response = client.post("/api/v1/coach/chat", json={"zone_id": "Empty " + probe_id,
                "question": "What incidents happened here? If no records were supplied, say so; do not invent any."})
            check(response.status_code == 200, "empty_zone_responded")
            data = response.json()
            check(data.get("mode") == "gemini" and data.get("context_count") == 0 and data.get("incident_ids") == [],
                "empty_zone_has_no_sources")
            result["answers"].append(data["answer"])
        return {**result, "status": "passed", "review": "Review both answers for factual grounding before stage acceptance"}
    except (ValueError, KeyError, TypeError):
        return {**result, "error": "verification_failed_after_last_recorded_check"}


if __name__ == "__main__":
    result = verify(Settings.from_env())
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "passed" else 1)
