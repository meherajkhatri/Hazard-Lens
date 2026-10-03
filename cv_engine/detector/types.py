"""Shared data types for the detector. Kept free of OpenCV/Ultralytics so the
fall logic can be unit-tested without a camera or a model."""

from dataclasses import dataclass
from enum import Enum

import numpy as np

# COCO-17 keypoint indices used by YOLOv8-pose.
L_SHOULDER, R_SHOULDER = 5, 6
L_HIP, R_HIP = 11, 12
L_ANKLE, R_ANKLE = 15, 16

BBox = tuple[float, float, float, float]  # x1, y1, x2, y2 in pixels


@dataclass(frozen=True)
class PersonPose:
    """One tracked person in one frame."""

    track_id: int
    keypoints: np.ndarray  # shape (17, 3): x, y, conf
    bbox: BBox


@dataclass(frozen=True)
class PoseFeatures:
    torso_angle_deg: float  # 0 = upright, 90 = horizontal
    bbox_aspect: float  # bbox width / height
    body_scale: float  # shoulder-mid -> ankle-mid distance, pixels
    hip_y: float  # hip-mid y, pixels (grows downward)
    keypoint_conf: float  # lowest conf among shoulders + hips


class FallState(str, Enum):
    UPRIGHT = "UPRIGHT"  # green box
    FALLING = "FALLING"  # amber box
    DOWN = "DOWN"  # red box


@dataclass(frozen=True)
class FallEvent:
    """One confirmed fall. Maps 1:1 to a `fall` telemetry payload."""

    track_id: int
    timestamp: float  # epoch seconds when DOWN was confirmed
    drop_started_at: float  # epoch seconds when the drop was first seen
    pose_confidence: float
    torso_angle_deg: float
    bbox_aspect: float
    drop_velocity: float  # peak, body-heights / second
    keypoint_conf: float
    bbox: BBox
