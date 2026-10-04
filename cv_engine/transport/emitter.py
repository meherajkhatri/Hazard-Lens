"""TelemetryEmitter: sends telemetry to the backend without blocking the camera loop.

Payloads match TelemetryEvent in backend/app/schemas.py (extra fields are
rejected there, so nothing outside that schema goes at the top level).
Falls are retried until delivered (oldest first); heartbeats are dropped if
they fail. Anything the backend rejects or ignores is logged as an error,
so a fall can never disappear silently.
"""

import logging
import queue
import threading
import time
from collections import deque
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

import requests

from cv_engine.detector.types import FallEvent, PostFallAssessment

log = logging.getLogger(__name__)

TELEMETRY_PATH = "/api/v1/telemetry"
# The backend answers a fall only after submitting the SMS, which can take
# several seconds; heartbeats should fail fast.
FALL_TIMEOUT_S = 15.0
HEARTBEAT_TIMEOUT_S = 2.0
RETRY_DELAYS_S = (0.25, 1.0)  # immediate retries per attempt
RESEND_INTERVAL_S = 2.0  # how often undelivered falls are retried
MAX_PENDING_FALLS = 100
UNREACHABLE_LOG_EVERY_S = 30.0  # while the backend is down, log it this often, not every retry


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def event_id(camera_id: str, event: FallEvent) -> str:
    """Deterministic UUID per fall, so retries are recognised as duplicates."""
    return str(uuid5(NAMESPACE_URL, f"call-help/{camera_id}/{event.track_id}/{int(event.timestamp * 1000)}"))


def fall_payload(
    event: FallEvent,
    camera_id: str,
    zone_id: str,
    sent_at: float,
    snapshot_base_url: str | None = None,
) -> dict:
    eid = event_id(camera_id, event)
    metadata = {
        "track_id": event.track_id,
        "torso_angle_deg": round(event.torso_angle_deg, 1),
        "bbox_aspect": round(event.bbox_aspect, 2),
        "drop_velocity": round(event.drop_velocity, 2),
        "keypoint_conf": round(event.keypoint_conf, 2),
        "latency_ms": int(round((sent_at - event.drop_started_at) * 1000)),
        "trigger": "manual" if event.manual else "auto",
        "detection": event.detection,
    }
    if snapshot_base_url:
        # Only included when known: metadata values may not be null.
        metadata["snapshot_url"] = f"{snapshot_base_url.rstrip('/')}/snapshot/{eid}.jpg"
    return {
        "event_id": eid,
        "camera_id": camera_id,
        "zone_id": zone_id,
        "timestamp": _iso(event.timestamp),
        "pose_confidence": round(event.pose_confidence, 3),
        "event_type": "fall",
        "metadata": metadata,
    }


def heartbeat_payload(camera_id: str, zone_id: str, now: float, fps: float, people_detected: int,
                      vision: str = "ok") -> dict:
    """Sent as event_type "normal", which the backend acknowledges without storing.

    `vision` is "ok" or the VisionMonitor reason ("glare", "dark", "haze").
    """
    return {
        "camera_id": camera_id,
        "zone_id": zone_id,
        "timestamp": _iso(now),
        "pose_confidence": 0.0,
        "event_type": "normal",
        "metadata": {"heartbeat": True, "fps": round(fps, 1), "people_detected": people_detected, "vision": vision},
    }


def is_heartbeat(payload: dict) -> bool:
    return payload.get("event_type") == "normal"


def assessment_path(incident_id: str) -> str:
    return f"/api/v1/incidents/{incident_id}/assessment"


def assessment_payload(assessment: PostFallAssessment, camera_id: str, zone_id: str) -> dict:
    """Body for POST /api/v1/incidents/{incident_id}/assessment (incident_id = the fall's event_id)."""
    return {
        "outcome": assessment.outcome.value,
        "seconds_down": round(assessment.seconds_down, 1),
        "motion": round(assessment.motion, 3),
        "observed_at": _iso(assessment.timestamp),
        "camera_id": camera_id,
        "zone_id": zone_id,
    }


class TelemetryEmitter:
    def __init__(self, backend_url: str, api_key: str = "") -> None:
        self.base_url = backend_url.rstrip("/")
        self.url = self.base_url + TELEMETRY_PATH
        self._queue: queue.Queue[dict | None] = queue.Queue()
        self._pending_falls: deque[dict] = deque(maxlen=MAX_PENDING_FALLS)
        self._session = requests.Session()
        if api_key:
            self._session.headers["X-API-Key"] = api_key
        self._thread = threading.Thread(target=self._run, name="telemetry-emitter", daemon=True)
        self.delivered = 0
        self._pending_assessments: deque[tuple[str, dict]] = deque(maxlen=MAX_PENDING_FALLS)
        self.assessments_delivered = 0
        self._warned_no_assessment_endpoint = False
        self._unreachable_since: float | None = None
        self._last_unreachable_log = float("-inf")
        self._suppressed_unreachable = 0
        self.rejected = 0  # falls the backend refused or ignored; should stay 0
        self._thread.start()

    def send(self, payload: dict) -> None:
        """Queue a payload. Returns immediately."""
        self._queue.put(payload)

    def send_assessment(self, incident_id: str, body: dict) -> None:
        """Queue a post-fall assessment for an incident. Sent after pending falls."""
        self._queue.put({"_assessment_for": incident_id, "body": body})

    @property
    def pending_falls(self) -> int:
        return len(self._pending_falls)

    def close(self, timeout: float = 3.0) -> None:
        """Flush what can be sent within `timeout`, then stop."""
        self._queue.put(None)
        self._thread.join(timeout)

    def _unreachable(self, what: str, exc: Exception) -> None:
        now = time.monotonic()
        if self._unreachable_since is None:
            self._unreachable_since = now
        if now - self._last_unreachable_log < UNREACHABLE_LOG_EVERY_S:
            self._suppressed_unreachable += 1
            return
        self._last_unreachable_log = now
        more = f" ({self._suppressed_unreachable} more failed tries)" if self._suppressed_unreachable else ""
        self._suppressed_unreachable = 0
        log.warning("backend unreachable at %s (%s, %s)%s; %d falls waiting. Check BACKEND_URL and run "
                    "python -m cv_engine.preflight", self.base_url, what, type(exc).__name__, more,
                    len(self._pending_falls))

    def _reachable(self) -> None:
        if self._unreachable_since is not None:
            log.info("backend reachable again after %.0fs", time.monotonic() - self._unreachable_since)
            self._unreachable_since = None
            self._last_unreachable_log = float("-inf")
            self._suppressed_unreachable = 0

    def _post(self, payload: dict, retry: bool = True) -> bool:
        """True when the payload is settled (accepted, or rejected for good)."""
        heartbeat = is_heartbeat(payload)
        timeout = HEARTBEAT_TIMEOUT_S if heartbeat else FALL_TIMEOUT_S
        for delay in (0.0, *RETRY_DELAYS_S) if retry else (0.0,):
            if delay:
                time.sleep(delay)
            try:
                response = self._session.post(self.url, json=payload, timeout=timeout)
            except requests.RequestException as exc:
                self._unreachable(payload["event_type"], exc)
                continue
            self._reachable()
            if response.ok:
                self.delivered += 1
                try:
                    status = response.json().get("status")
                except ValueError:
                    status = None
                if not heartbeat and status not in ("received", "duplicate"):
                    self.rejected += 1
                    log.error("backend did NOT record fall %s: %s", payload.get("event_id"), response.text[:300])
                return True
            if 400 <= response.status_code < 500:
                if not heartbeat:
                    self.rejected += 1
                hint = " (check API_KEY)" if response.status_code == 401 else ""
                log.error("backend rejected %s%s: %s %s", payload["event_type"], hint,
                          response.status_code, response.text[:300])
                return True  # retrying won't fix a rejected payload; drop it
            log.warning("backend error %s for %s", response.status_code, payload["event_type"])
        return False

    def _flush_pending(self) -> None:
        while self._pending_falls:
            if not self._post(self._pending_falls[0]):
                return
            self._pending_falls.popleft()
        # An assessment needs its incident to exist, so only after falls are out.
        while self._pending_assessments:
            if not self._post_assessment(*self._pending_assessments[0]):
                return
            self._pending_assessments.popleft()

    def _post_assessment(self, incident_id: str, body: dict) -> bool:
        """True when settled (delivered, or refused for good)."""
        try:
            response = self._session.post(self.base_url + assessment_path(incident_id), json=body,
                                          timeout=FALL_TIMEOUT_S)
        except requests.RequestException as exc:
            self._unreachable("assessment", exc)
            return False
        self._reachable()
        if response.ok:
            self.assessments_delivered += 1
            return True
        if response.status_code in (404, 405):
            if not self._warned_no_assessment_endpoint:
                self._warned_no_assessment_endpoint = True
                log.warning("backend has no %s endpoint yet; post-fall outcomes show on the stream only",
                            assessment_path("{incident_id}"))
            return True
        if 400 <= response.status_code < 500:
            log.error("backend rejected assessment for %s: %s %s", incident_id, response.status_code,
                      response.text[:300])
            return True
        log.warning("backend error %s for assessment", response.status_code)
        return False

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
            items = [p for p in batch if p is not None]
            heartbeats = [p for p in items if is_heartbeat(p)]
            self._pending_assessments.extend((p["_assessment_for"], p["body"]) for p in items if "_assessment_for" in p)
            self._pending_falls.extend(p for p in items if not is_heartbeat(p) and "_assessment_for" not in p)
            self._flush_pending()
            # Only the latest heartbeat matters, and never ahead of undelivered falls.
            if heartbeats and not self._pending_falls and not self._pending_assessments:
                self._post(heartbeats[-1], retry=False)
            if stopping:
                return
