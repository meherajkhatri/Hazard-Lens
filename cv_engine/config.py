"""All tunable settings for the CV engine.

Engine settings come from environment variables so each laptop can override
them without code changes. FallThresholds are the knobs to tune at the venue.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # optional: plain environment variables still work
    load_dotenv = None

# Secrets such as API_KEY live in cv_engine/.env (gitignored), never in code.
ENV_FILE = Path(__file__).resolve().parent / ".env"
if load_dotenv and ENV_FILE.exists():
    load_dotenv(ENV_FILE)


@dataclass(frozen=True)
class FallThresholds:
    # Frames whose shoulders + hips average below this confidence are skipped.
    MIN_KEYPOINT_CONF: float = 0.4

    # UPRIGHT -> FALLING: hips move down at least this fast (body-heights / second),
    # measured over the last FALL_DROP_WINDOW_S seconds.
    FALL_DROP_VELOCITY: float = 0.5
    FALL_DROP_WINDOW_S: float = 0.6

    # "Horizontal" = torso tilted at least this far AND box at least this wide.
    DOWN_TORSO_MIN_DEG: float = 60.0
    DOWN_ASPECT_MIN: float = 1.0

    # FALLING -> DOWN: horizontal for this long. Emits one FallEvent.
    DOWN_CONFIRM_S: float = 1.0
    # FALLING -> UPRIGHT: not horizontal this long after the drop (crouch or sit).
    FALLING_TIMEOUT_S: float = 1.5

    # DOWN -> UPRIGHT: torso back within this angle for this long.
    UPRIGHT_TORSO_MAX_DEG: float = 30.0
    RECOVER_CONFIRM_S: float = 1.0

    # No second FallEvent for the same track_id within this window.
    EVENT_COOLDOWN_S: float = 15.0
    # Forget tracks not seen for this long.
    TRACK_TTL_S: float = 3.0


@dataclass(frozen=True)
class EngineConfig:
    CAMERA_ID: str = os.getenv("CAMERA_ID", "zone-1-cam-1")
    ZONE_ID: str = os.getenv("ZONE_ID", "Zone 1")
    CAMERA_INDEX: int = int(os.getenv("CAMERA_INDEX", "0"))
    BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")
    # Must match the backend's API_KEY (sent as X-API-Key). Empty if the backend has none.
    API_KEY: str = os.getenv("API_KEY", "")
    STREAM_PORT: int = int(os.getenv("STREAM_PORT", "8001"))
    MODEL_PATH: str = os.getenv("MODEL_PATH", "yolov8n-pose.pt")
    # "cuda" (Nvidia), "mps" (Apple Silicon) or "cpu".
    DEVICE: str = os.getenv("DEVICE", "cpu")
    # Host other laptops use to reach this one, for snapshot_url. Auto-detected if empty.
    PUBLIC_HOST: str = os.getenv("PUBLIC_HOST", "")
    HEARTBEAT_INTERVAL_S: float = 5.0
    thresholds: FallThresholds = field(default_factory=FallThresholds)
