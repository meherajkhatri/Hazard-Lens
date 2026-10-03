"""Check that this laptop can reach the backend before going live.

    python -m cv_engine.preflight

Verifies, in order: the backend answers, the API key is accepted, and a
heartbeat is processed. Each failure prints the likely fix.
"""

import sys
import time
from urllib.parse import urlparse

import requests

from cv_engine.config import EngineConfig
from cv_engine.transport.emitter import TELEMETRY_PATH, heartbeat_payload

TIMEOUT_S = 3.0


def check(cfg: EngineConfig) -> list[str]:
    """Return a list of problems; empty means ready."""
    base = cfg.BACKEND_URL.rstrip("/")
    headers = {"X-API-Key": cfg.API_KEY} if cfg.API_KEY else {}
    host = urlparse(base).hostname or ""

    try:
        health = requests.get(f"{base}/health", timeout=TIMEOUT_S)
        health.raise_for_status()
    except requests.RequestException as exc:
        fixes = [
            f"Cannot reach the backend at {base} ({type(exc).__name__}).",
            "On Dev 2's laptop, start it so other laptops can connect:",
            "  uvicorn app.main:app --host 0.0.0.0 --port 8000",
            "Allow port 8000 through Dev 2's firewall (Windows asks the first time; click Allow).",
            "Put both laptops on the same network; campus/venue Wi-Fi often blocks laptop-to-laptop traffic, so use a phone hotspot.",
        ]
        if host in ("localhost", "127.0.0.1"):
            fixes.insert(1, "BACKEND_URL points at this laptop. Set it to Dev 2's IP in cv_engine/.env, e.g. BACKEND_URL=http://192.168.1.20:8000")
        return fixes

    ready = requests.get(f"{base}/api/v1/ready", headers=headers, timeout=TIMEOUT_S)
    if ready.status_code == 401:
        return ["Backend rejected the API key. Copy API_KEY from Dev 2's backend .env into cv_engine/.env exactly."]
    if not ready.ok:
        return [f"Backend is up but not ready ({ready.status_code}): {ready.text[:200]}",
                "Usually storage: check Dev 2's SQLite path or Supabase settings."]

    beat = requests.post(f"{base}{TELEMETRY_PATH}", headers=headers, timeout=TIMEOUT_S,
                         json=heartbeat_payload(cfg.CAMERA_ID, cfg.ZONE_ID, time.time(), 0.0, 0))
    if not beat.ok:
        return [f"Backend refused a heartbeat ({beat.status_code}): {beat.text[:200]}",
                "The CV engine and backend disagree on the telemetry format; pull the latest main on both laptops."]
    return []


def main() -> None:
    cfg = EngineConfig()
    print(f"Backend: {cfg.BACKEND_URL}   API key: {'set' if cfg.API_KEY else 'NOT SET'}")
    problems = check(cfg)
    if problems:
        print("NOT READY")
        for line in problems:
            print("  " + line)
        sys.exit(1)
    print("READY: backend reachable, API key accepted, telemetry format matches.")


if __name__ == "__main__":
    main()
