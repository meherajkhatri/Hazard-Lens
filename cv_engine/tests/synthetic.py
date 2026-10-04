"""Builds stick-figure PersonPose objects so tests run without a camera."""

import math

import numpy as np

from cv_engine.detector.types import (
    L_ANKLE,
    L_HIP,
    L_SHOULDER,
    R_ANKLE,
    R_HIP,
    R_SHOULDER,
    PersonPose,
)

BODY_PX = 300.0  # standing shoulder -> ankle height
TORSO_PX = 100.0
SHOULDER_HALF_WIDTH_PX = 25.0


def make_pose(
    track_id: int = 1,
    hip_y: float = 400.0,
    angle_deg: float = 0.0,
    hip_x: float = 320.0,
    conf: float = 0.9,
    ankle_conf: float = 0.9,
    squash: float = 1.0,
) -> PersonPose:
    """A person whose torso is tilted `angle_deg` from vertical (0 = standing).

    `squash` < 1 shrinks the body vertically in the image, as when someone lies
    pointing toward or away from a high camera (foreshortening).
    """
    a = math.radians(angle_deg)
    up = np.array([math.sin(a), -math.cos(a) * squash])  # hip -> shoulder direction
    side = np.array([math.cos(a), math.sin(a)])  # across the shoulders
    hip = np.array([hip_x, hip_y])
    shoulder = hip + up * TORSO_PX
    ankle = hip - up * (BODY_PX - TORSO_PX)

    kps = np.zeros((17, 3))
    kps[L_SHOULDER] = [*(shoulder - side * SHOULDER_HALF_WIDTH_PX), conf]
    kps[R_SHOULDER] = [*(shoulder + side * SHOULDER_HALF_WIDTH_PX), conf]
    kps[L_HIP] = [*(hip - side * SHOULDER_HALF_WIDTH_PX * 0.8), conf]
    kps[R_HIP] = [*(hip + side * SHOULDER_HALF_WIDTH_PX * 0.8), conf]
    kps[L_ANKLE] = [*(ankle - side * 15), ankle_conf]
    kps[R_ANKLE] = [*(ankle + side * 15), ankle_conf]

    head = shoulder + up * 40
    pts = np.array([shoulder, hip, ankle, head])
    pad = 30.0
    x1, y1 = pts.min(axis=0) - pad
    x2, y2 = pts.max(axis=0) + pad
    return PersonPose(track_id=track_id, keypoints=kps, bbox=(x1, y1, x2, y2))
