"""Send one simulated fall to a running backend."""
import argparse
from datetime import datetime, timezone
from uuid import uuid4

import httpx

from app.config import Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--zone", default="Zone 1")
    args = parser.parse_args()
    settings = Settings.from_env()
    with httpx.Client(base_url=args.url, timeout=40, headers={"X-API-Key": settings.api_key}) as client:
        health = client.get("/health")
        health.raise_for_status()
        response = client.post("/api/v1/telemetry", json={"event_id": str(uuid4()),
            "camera_id": "demo-webcam-1", "zone_id": args.zone,
            "timestamp": datetime.now(timezone.utc).isoformat(), "pose_event": "fall",
            "confidence_score": 0.96, "metadata": {"simulated": True}})
        response.raise_for_status()
        print(response.text)


if __name__ == "__main__":
    main()
