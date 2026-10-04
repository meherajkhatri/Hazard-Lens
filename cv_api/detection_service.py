import json
import logging
import threading
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
import requests
import torch

from cv_engine.config import FallThresholds
from cv_engine.detector.fall_state import FallDetector
from cv_engine.detector.features import compute_features
from cv_engine.detector.pose import PoseEstimator
from cv_engine.detector.types import FallState

from cv_api.config import ApiConfig

log = logging.getLogger("hazard_lens.cv_api")


def choose_device(requested: str) -> str:
    requested = requested.lower()
    if requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    mps = getattr(torch.backends, "mps", None)
    if mps is not None and mps.is_available():
        return "mps"
    return "cpu"


class DetectionService:
    """Thread-safe inference wrapper around Hazard Lens' existing CV engine."""

    def __init__(self, config: ApiConfig):
        self.config = config
        self.device = choose_device(config.device)
        self.lock = threading.Lock()
        self.pose: PoseEstimator | None = None
        self.detector: FallDetector | None = None
        self.model_error: str | None = None
        self.confirmed_tracks: set[int] = set()
        self.last_inference_ms = 0.0
        self._load_model()

    def _load_model(self) -> None:
        try:
            thresholds = replace(
                FallThresholds(),
                DOWN_CONFIRM_S=self.config.fall_confirmation_seconds,
            )
            self.pose = PoseEstimator(
                model_path=self.config.model_path,
                device=self.device,
                imgsz=640,
            )
            self.detector = FallDetector(thresholds)
            log.info("CV model ready on %s", self.device)
        except Exception as exc:
            self.model_error = str(exc)
            log.exception("CV model failed to load")

    @property
    def ready(self) -> bool:
        return self.pose is not None and self.detector is not None and self.model_error is None

    def health(self) -> dict:
        return {
            "status": "ok" if self.ready else "degraded",
            "model_ready": self.ready,
            "model": self.config.model_path,
            "device": self.device,
            "emergency_mode": self.config.emergency_mode,
            "test_mode": self.config.test_mode,
            "confirmation_seconds": self.config.fall_confirmation_seconds,
            "confidence_threshold": self.config.fall_confidence_threshold,
            "last_inference_ms": round(self.last_inference_ms, 1),
            "error": self.model_error,
        }

    @staticmethod
    def decode_image(raw: bytes) -> np.ndarray:
        if not raw:
            raise ValueError("Empty image")
        array = np.frombuffer(raw, dtype=np.uint8)
        frame = cv2.imdecode(array, cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("Invalid image")
        return frame

    def detect(self, raw: bytes, zone_id: str | None = None) -> dict:
        if not self.ready:
            raise RuntimeError(self.model_error or "Model unavailable")
        frame = self.decode_image(raw)
        started = time.perf_counter()
        now = time.time()

        with self.lock:
            people = self.pose(frame)
            events = self.detector.update(people, now)

            present_ids = {person.track_id for person in people}
            self.confirmed_tracks.intersection_update(present_ids)
            confirmed_events = []
            for event in events:
                if event.pose_confidence >= self.config.fall_confidence_threshold:
                    self.confirmed_tracks.add(event.track_id)
                    confirmed_events.append(event)
                    self._record_event(event, zone_id or self.config.default_zone)

            persons = []
            any_falling = False
            any_down = False
            confidence = 0.0
            for person in people:
                state = self.detector.state_of(person.track_id)
                features = compute_features(person)
                keypoint_conf = features.keypoint_conf if features else 0.0
                confidence = max(confidence, keypoint_conf)
                any_falling = any_falling or state is FallState.FALLING
                any_down = any_down or state is FallState.DOWN
                persons.append({
                    "track_id": person.track_id,
                    "bbox": [round(v, 1) for v in person.bbox],
                    "state": state.value.lower(),
                    "confidence": round(keypoint_conf, 3),
                })

            active_confirmed = bool(self.confirmed_tracks & present_ids)
            if confirmed_events:
                confidence = max(confidence, max(event.pose_confidence for event in confirmed_events))

            if active_confirmed:
                status = "fall_detected"
            elif any_falling or any_down:
                status = "possible_fall"
            elif people:
                status = "person_detected"
            else:
                status = "normal"

        self.last_inference_ms = (time.perf_counter() - started) * 1000
        return {
            "success": True,
            "person_detected": bool(people),
            "fall_detected": active_confirmed,
            "confidence": round(float(confidence), 3),
            "status": status,
            "people": persons,
            "frame": {"width": int(frame.shape[1]), "height": int(frame.shape[0])},
            "inference_ms": round(self.last_inference_ms, 1),
            "emergency_mode": self.config.emergency_mode,
        }

    def _record_event(self, event, zone_id: str) -> None:
        payload = {
            "event_id": str(uuid4()),
            "camera_id": self.config.camera_id,
            "zone_id": zone_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "fall",
            "pose_confidence": round(float(event.pose_confidence), 4),
            "metadata": {
                "source": "browser_camera_flask",
                "test_mode": not self.config.emergency_mode,
                "track_id": event.track_id,
                "torso_angle_deg": round(float(event.torso_angle_deg), 2),
                "bbox_aspect": round(float(event.bbox_aspect), 3),
                "drop_velocity": round(float(event.drop_velocity), 3),
            },
        }

        path = Path(self.config.event_log)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")

        if not self.config.emergency_mode:
            log.warning("TEST MODE fall logged locally; no external alert sent")
            return

        try:
            response = requests.post(
                f"{self.config.backend_url}/api/v1/telemetry",
                json=payload,
                headers={"X-API-Key": self.config.api_key},
                timeout=4,
            )
            response.raise_for_status()
        except requests.RequestException:
            log.exception("Fall confirmed but backend notification failed")

    def simulated_fall(self, zone_id: str | None = None) -> dict:
        if not self.config.test_mode:
            raise PermissionError("TEST_MODE is disabled")
        return {
            "success": True,
            "person_detected": True,
            "fall_detected": True,
            "confidence": 0.99,
            "status": "fall_detected",
            "people": [{
                "track_id": -1,
                "bbox": [120, 210, 520, 410],
                "state": "down",
                "confidence": 0.99,
            }],
            "frame": {"width": 640, "height": 480},
            "inference_ms": 0.0,
            "emergency_mode": False,
            "simulated": True,
            "zone_id": zone_id or self.config.default_zone,
        }
