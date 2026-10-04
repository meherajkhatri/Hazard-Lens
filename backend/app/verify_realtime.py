"""Real HTTP/WebSocket integration probe. Always dry-run SMS; no Gemini calls."""
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

import httpx
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from app.config import Settings


class VerificationFailure(Exception):
    pass


async def exercise(base_url, api_key, result):
    def check(condition, name):
        if not condition:
            raise VerificationFailure(name)
        result["checks"].append(name)

    async def receive(ws):
        return json.loads(await asyncio.wait_for(ws.recv(), timeout=20))

    async def authenticate(ws):
        await ws.send(json.dumps({"api_key": api_key}))
        if (await receive(ws)).get("type") != "connected":
            raise VerificationFailure("websocket_auth")

    ws_url = base_url.replace("http://", "ws://")
    async with httpx.AsyncClient(base_url=base_url, timeout=20, headers={"X-API-Key": api_key}) as client:
        check((await client.get("/api/v1/ready")).status_code == 200, "live_storage_ready")
        async with connect(ws_url + "/ws/telemetry", proxy=None) as unauthorized:
            await unauthorized.send(json.dumps({"api_key": "wrong-" + api_key}))
            try:
                await receive(unauthorized)
            except ConnectionClosed as exc:
                check(exc.rcvd is not None and exc.rcvd.code == 1008, "wrong_key_rejected")
            else:
                raise VerificationFailure("wrong_key_accepted")

        probe_id = result["probe_id"]
        zone = "Realtime Verification " + probe_id
        payload = {"event_id": probe_id, "camera_id": "probe-" + probe_id, "zone_id": zone,
            "timestamp": datetime.now(timezone.utc).isoformat(), "pose_event": "fall",
            "confidence_score": 0.7, "metadata": {"simulated": True, "realtime_probe": True}}
        async with connect(ws_url + "/ws/incidents", proxy=None) as dashboard:
            await authenticate(dashboard)
            async with connect(ws_url + "/ws/telemetry", proxy=None) as camera:
                await authenticate(camera)
                await camera.send("not-json")
                check((await receive(camera)).get("status") == 422, "invalid_payload_rejected")
                start = time.perf_counter()
                await camera.send(json.dumps(payload))
                created = await receive(dashboard)
                result["broadcast_latency_ms"] = round((time.perf_counter() - start) * 1000, 1)
                check(created.get("type") == "incident.created" and
                    created.get("incident", {}).get("incident_id") == probe_id, "camera_to_dashboard_broadcast")
                ack = await receive(camera)
                check(ack.get("status") == "received" and ack["incident"]["sms_status"] == "dry_run",
                    "camera_ack_and_dry_run")
                updated = await receive(dashboard)
                check(updated.get("type") == "incident.updated" and
                    updated["incident"]["sms_status"] == "dry_run", "sms_status_broadcast")
                await camera.send(json.dumps(payload))
                check((await receive(camera)).get("status") == "duplicate", "websocket_retry_deduplicated")
        # Reconnect the dashboard, then restore state via the supported REST resync contract.
        async with connect(ws_url + "/ws/incidents", proxy=None) as dashboard:
            await authenticate(dashboard)
            response = await client.get("/api/v1/incidents", params={"zone_id": zone})
            check(response.status_code == 200 and len(response.json()) == 1 and
                response.json()[0]["incident_id"] == probe_id, "reconnect_rest_resync")
            coach = await client.post("/api/v1/coach/chat", json={"question": "Summarize this event", "zone_id": zone})
            check(coach.status_code == 200 and coach.json().get("incident_ids") == [probe_id] and
                coach.json().get("mode") == "local_summary", "coach_retrieves_new_incident")
            resolved = await client.patch(f"/api/v1/incidents/{probe_id}", json={"status": "resolved"})
            check(resolved.status_code == 200 and resolved.json()["status"] == "resolved", "probe_resolved")
            updated = await receive(dashboard)
            check(updated.get("type") == "incident.updated" and updated["incident"]["status"] == "resolved",
                "resolution_broadcast")


def verify(settings, exercise_fn=exercise):
    result = {"status": "failed", "storage": settings.storage, "sms_mode": "dry_run",
        "coach_mode": "local_summary", "probe_id": str(uuid4()), "checks": [],
        "transport": "real_uvicorn_http_and_websockets"}
    key = settings.api_key or str(uuid4())
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    # Pass explicit values so a developer's .env cannot silently enable external SMS/AI calls.
    environment = {**os.environ, "API_KEY": key, "STORAGE_BACKEND": settings.storage,
        "SQLITE_PATH": str(Path(settings.sqlite_path).resolve()), "SUPABASE_URL": settings.supabase_url,
        "SUPABASE_SECRET_KEY": settings.supabase_key, "SMS_MODE": "dry_run", "ALERT_PROVIDER": "twilio",
        "SMS_CHANNEL": "sms",
        "SMS_RECIPIENTS": "+15555550123", "TWILIO_FROM_NUMBER": "", "GEMINI_API_KEY": "",
        "MIN_CONFIDENCE": "0.7", "ALERT_COOLDOWN_SECONDS": "0"}
    with tempfile.TemporaryFile(mode="w+") as log:
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
            "--port", str(port), "--ws-max-size", "65536"], cwd=Path(__file__).resolve().parents[1],
            env=environment, stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            base_url = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + 20
            with httpx.Client(base_url=base_url, timeout=1) as client:
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise VerificationFailure("server_exited")
                    try:
                        if client.get("/health").status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(.1)
                else:
                    raise VerificationFailure("server_start_timeout")
            asyncio.run(exercise_fn(base_url, key, result))
            result["status"] = "passed"
        except VerificationFailure as exc:
            result["error"] = str(exc)
        except (httpx.HTTPError, ConnectionClosed, TimeoutError, OSError, ValueError, KeyError):
            result["error"] = "transport_or_response_failure_after_last_recorded_check"
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    return result


if __name__ == "__main__":
    result = verify(Settings.from_env())
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "passed" else 1)
