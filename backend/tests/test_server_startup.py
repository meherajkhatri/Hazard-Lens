"""Verify the real Uvicorn process and HTTP listener, not just TestClient."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx


def test_real_server_starts_with_local_storage_and_auth(tmp_path):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    environment = {**os.environ, "STORAGE_BACKEND": "sqlite",
        "SQLITE_PATH": str(tmp_path / "startup.sqlite3"), "API_KEY": "startup-test-key",
<<<<<<< Updated upstream
        "SMS_MODE": "dry_run", "SMS_RECIPIENTS": "", "TWILIO_FROM_NUMBER": "",
=======
        "ALERT_PROVIDER": "none",
>>>>>>> Stashed changes
        "GEMINI_API_KEY": "", "MIN_CONFIDENCE": "0.7", "ALERT_COOLDOWN_SECONDS": "30"}
    command = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
        "--port", str(port), "--ws-max-size", "65536"]
    with (tmp_path / "server.log").open("w+") as log:
        process = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1], env=environment,
            stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=1) as client:
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    assert process.poll() is None, "Uvicorn exited before becoming ready"
                    try:
                        health = client.get("/health")
                        if health.status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(.1)
                else:
                    raise AssertionError("Uvicorn did not start within 15 seconds")
                assert health.json()["storage"] == "sqlite"
                assert client.get("/api/v1/ready").status_code == 401
                assert client.get("/api/v1/ready", headers={"X-API-Key": "startup-test-key"}).json() == {"status": "ready"}
                schema = client.get("/openapi.json").json()
                assert "/api/v1/telemetry" in schema["paths"]
                assert "zone_id" in schema["components"]["schemas"]["TelemetryEvent"]["required"]
                assert (tmp_path / "startup.sqlite3").is_file()
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
