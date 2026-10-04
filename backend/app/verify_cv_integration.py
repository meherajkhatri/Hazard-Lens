"""Exercise Dev 1's actual REST sender through the backend to a WebSocket subscriber."""
import asyncio
import json
from pathlib import Path
import sys
import time

import httpx
from websockets.asyncio.client import connect

from app.config import Settings
from app.verify_realtime import VerificationFailure, verify

# The CV engine is a sibling package, not a backend runtime dependency.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from cv_engine.detector.types import FallEvent
from cv_engine.transport.emitter import TelemetryEmitter, fall_payload, heartbeat_payload


async def exercise_cv(base_url, api_key, result):
    result["transport"] = "dev1_rest_emitter_to_backend_websocket"
    def check(condition, name):
        if not condition:
            raise VerificationFailure(name)
        result["checks"].append(name)
    async def receive(ws):
        return json.loads(await asyncio.wait_for(ws.recv(), timeout=20))

    now = time.time()
    camera_id = "cv-probe-" + result["probe_id"]
    zone = "CV Integration " + result["probe_id"]
    event = FallEvent(track_id=1, timestamp=now, drop_started_at=now-1.2,
        pose_confidence=.7, torso_angle_deg=85, bbox_aspect=1.5, drop_velocity=.9,
        keypoint_conf=.9, bbox=(10, 20, 300, 220), manual=True)
    payload = fall_payload(event, camera_id, zone, sent_at=now+.04, snapshot_base_url="http://127.0.0.1:8001")
    payload["metadata"]["simulated"] = True
    result["probe_id"] = payload["event_id"]
    async with httpx.AsyncClient(base_url=base_url, headers={"X-API-Key": api_key}, timeout=20) as client:
        check((await client.get("/api/v1/ready")).status_code == 200, "storage_ready")
        async with connect(base_url.replace("http://", "ws://") + "/ws/incidents", proxy=None) as dashboard:
            await dashboard.send(json.dumps({"api_key": api_key}))
            check((await receive(dashboard)).get("type") == "connected", "dashboard_authenticated")
            emitter = TelemetryEmitter(base_url, api_key=api_key)
            try:
                start = time.perf_counter()
                emitter.send(payload)
                created = await receive(dashboard)
                result["broadcast_latency_ms"] = round((time.perf_counter()-start)*1000, 1)
                check(created.get("type") == "incident.created" and
                    created["incident"]["incident_id"] == payload["event_id"], "dev1_fall_broadcast")
                check((await receive(dashboard))["incident"]["alert_status"] == "not_configured", "alert_status")
                emitter.send(payload)  # identical retry must not create a second incident
                emitter.send(heartbeat_payload(camera_id, zone, now+1, fps=30, people_detected=1))
                deadline = time.monotonic()+20
                while emitter.delivered < 3 and time.monotonic() < deadline:
                    await asyncio.sleep(.05)
                check(emitter.delivered == 3 and emitter.rejected == 0, "fall_retry_and_heartbeat_accepted")
                response = await client.get("/api/v1/incidents", params={"zone_id": zone})
                rows = response.json()
                check(response.status_code == 200 and len(rows) == 1, "single_persisted_incident")
                check(rows[0]["metadata"] == payload["metadata"], "cv_metadata_and_snapshot_url_preserved")
                path = "/api/v1/incidents/" + payload["event_id"]
                check((await client.patch(path, json={"status": "resolved"})).json()["status"] == "resolved", "probe_resolved")
                check((await receive(dashboard))["incident"]["status"] == "resolved", "resolution_broadcast")
            finally:
                await asyncio.to_thread(emitter.close, 20)


if __name__ == "__main__":
    result = verify(Settings.from_env(), exercise_fn=exercise_cv)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "passed" else 1)
