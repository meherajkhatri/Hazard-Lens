import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ENV_FILE = Path(__file__).resolve().parent / ".env"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)


def _truthy(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ApiConfig:
    host: str = os.getenv("CV_API_HOST", "0.0.0.0")
    port: int = int(os.getenv("CV_API_PORT", "5000"))
    model_path: str = os.getenv("MODEL_PATH", "yolov8n-pose.pt")
    device: str = os.getenv("DEVICE", "auto")
    fall_confidence_threshold: float = float(os.getenv("FALL_CONFIDENCE_THRESHOLD", "0.68"))
    fall_confirmation_seconds: float = float(os.getenv("FALL_CONFIRMATION_SECONDS", "0.60"))
    min_keypoint_conf: float = float(os.getenv("MIN_KEYPOINT_CONF", "0.25"))
    fall_drop_velocity: float = float(os.getenv("FALL_DROP_VELOCITY", "0.28"))
    down_torso_min_deg: float = float(os.getenv("DOWN_TORSO_MIN_DEG", "45"))
    down_aspect_min: float = float(os.getenv("DOWN_ASPECT_MIN", "0.75"))
    collapse_height_ratio: float = float(os.getenv("COLLAPSE_HEIGHT_RATIO", "0.68"))

    near_miss_enabled: bool = _truthy("NEAR_MISS_ENABLED", "true")
    vehicle_model_path: str = os.getenv("VEHICLE_MODEL_PATH", "yolov8n.pt")
    near_miss_distance_ratio: float = float(os.getenv("NEAR_MISS_DISTANCE_RATIO", "0.18"))
    near_miss_confirmation_frames: int = int(os.getenv("NEAR_MISS_CONFIRMATION_FRAMES", "2"))
    vehicle_confidence_threshold: float = float(os.getenv("VEHICLE_CONFIDENCE_THRESHOLD", "0.30"))
    emergency_mode: bool = _truthy("EMERGENCY_MODE", "false")
    test_mode: bool = _truthy("TEST_MODE", "true")
    camera_id: str = os.getenv("CAMERA_ID", "browser-cam-1")
    default_zone: str = os.getenv("ZONE_ID", "Zone 1")
    backend_url: str = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
    api_key: str = os.getenv("API_KEY", "")
    cors_origins: tuple[str, ...] = tuple(
        part.strip()
        for part in os.getenv(
            "CV_CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000",
        ).split(",")
        if part.strip()
    )
    event_log: str = os.getenv("EVENT_LOG", "backend/data/cv_api_falls.jsonl")

    def validate(self) -> None:
        if not 0.0 <= self.fall_confidence_threshold <= 1.0:
            raise ValueError("FALL_CONFIDENCE_THRESHOLD must be between 0 and 1")
        if self.fall_confirmation_seconds <= 0:
            raise ValueError("FALL_CONFIRMATION_SECONDS must be greater than 0")
        if self.near_miss_confirmation_frames < 1:
            raise ValueError("NEAR_MISS_CONFIRMATION_FRAMES must be at least 1")
