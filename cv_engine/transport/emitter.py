"""TelemetryEmitter: sends telemetry to the backend without blocking the camera loop.

Payloads match TelemetryEvent in backend/app/schemas.py. Falls are retried
until delivered (oldest first); heartbeats are dropped if they fail.
"""

import logging
import queue
import threading
import time
from collections import deque
from datetime import datetime, timezone

import requests

from cv_engine.detector.types import FallEvent

log = logging.getLogger(__name__)

TELEMETRY_PATH = "/api/v1/telemetry"
REQUEST_TIMEOUT_S = 2.0
RETRY_DELAYS_S = (0.25, 1.0)  # immediate retries per attempt
RESEND_INTERVAL_S = 2.0  # how often undelivered falls are retried
MAX_PENDING_FALLS = 100


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def event_id(camera_id: str, event: FallEvent) -> str:
    return f"{camera_id}-{event.track_id}-{int(event.timestamp * 1000)}"


def fall_payload(
    event: FallEvent,
    camera_id: str,
    zone_id: str,
    sent_at: float,
    snapshot_base_url: str | None = None,
) -> dict:
    eid = event_id(camera_id, event)
    metadata = {
        "event_id": eid,
        "zone_id": zone_id,
        "track_id": event.track_id,
        "torso_angle_deg": round(event.torso_angle_deg, 1),
        "bbox_aspect": round(event.bbox_aspect, 2),
        "drop_velocity": round(event.drop_velocity, 2),
        "keypoint_conf": round(event.keypoint_conf, 2),
        "latency_ms": int(round((sent_at - event.drop_started_at) * 1000)),
        "trigger": "manual" if event.manual else "auto",
    }
    if snapshot_base_url:
        # Only included when known: metadata values may not be null.
        metadata["snapshot_url"] = f"{snapshot_base_url.rstrip('/')}/snapshot/{eid}.jpg"
    return {
        "camera_id": camera_id,
        "timestamp": _iso(event.timestamp),
        "pose_confidence": round(event.pose_confidence, 3),
        "event_type": "fall",
        "metadata": metadata,
    }


def heartbeat_payload(camera_id: str, zone_id: str, now: float, fps: float, people_detected: int) -> dict:
    return {
        "camera_id": camera_id,
        "timestamp": _iso(now),
        "pose_confidence": 0.0,
        "event_type": "heartbeat",
        "metadata": {"zone_id": zone_id, "fps": round(fps, 1), "people_detected": people_detected},
    }


class TelemetryEmitter:
    def __init__(self, backend_url: str) -> None:
        self.url = backend_url.rstrip("/") + TELEMETRY_PATH
        self._queue: queue.Queue[dict | None] = queue.Queue()
        self._pending_falls: deque[dict] = deque(maxlen=MAX_PENDING_FALLS)
        self._session = requests.Session()
        self._thread = threading.Thread(target=self._run, name="telemetry-emitter", daemon=True)
        self.delivered = 0
        self._thread.start()

    def send(self, payload: dict) -> None:
        """Queue a payload. Returns immediately."""
        self._queue.put(payload)

    @property
    def pending_falls(self) -> int:
        return len(self._pending_falls)

    def close(self, timeout: float = 3.0) -> None:
        """Flush what can be sent within `timeout`, then stop."""
        self._queue.put(None)
        self._thread.join(timeout)

    def _post(self, payload: dict, retry: bool = True) -> bool:
        for delay in (0.0, *RETRY_DELAYS_S) if retry else (0.0,):
            if delay:
                time.sleep(delay)
            try:
                response = self._session.post(self.url, json=payload, timeout=REQUEST_TIMEOUT_S)
                if response.ok:
                    self.delivered += 1
                    return True
                log.warning("backend rejected %s: %s %s", payload["event_type"], response.status_code, response.text[:200])
                if 400 <= response.status_code < 500:
                    return True  # retrying a malformed payload won't help; drop it
            except requests.RequestException as exc:
                log.warning("backend unreachable (%s): %s", payload["event_type"], exc)
        return False

    def _flush_pending(self) -> None:
        while self._pending_falls:
            if not self._post(self._pending_falls[0]):
                return
            self._pending_falls.popleft()

    def _run(self) -> None:
        while True:
            try:
                batch = [self._queue.get(timeout=RESEND_INTERVAL_S)]
            except queue.Empty:
                self._flush_pending()
                continue
            # Take everything already queued, so an outage costs one retry cycle
            # for the whole backlog instead of one per event.
            while True:
                try:
                    batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break

            stopping = None in batch
            heartbeats = [p for p in batch if p is not None and p["event_type"] == "heartbeat"]
            self._pending_falls.extend(p for p in batch if p is not None and p["event_type"] != "heartbeat")
            self._flush_pending()
            # Only the latest heartbeat matters, and never ahead of undelivered falls.
            if heartbeats and not self._pending_falls:
                self._post(heartbeats[-1], retry=False)
            if stopping:
                return
