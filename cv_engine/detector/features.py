"""Per-frame geometry for fall detection. Pure numpy, no camera needed."""

import math
from collections.abc import Iterable

import numpy as np

from cv_engine.detector.types import (
    L_ANKLE,
    L_HIP,
    L_SHOULDER,
    R_ANKLE,
    R_HIP,
    R_SHOULDER,
    PersonPose,
    PoseFeatures,
)

ANKLE_MIN_CONF = 0.3
# A shoulder or hip counts as visible from this confidence (same as MIN_KEYPOINT_CONF).
JOINT_MIN_CONF = 0.4
# Shoulder-hip distance is roughly 1/3 of standing height.
TORSO_TO_BODY_RATIO = 3.0
# Guard against ankles mis-detected near the hips shrinking body_scale.
MIN_BODY_TO_TORSO_RATIO = 2.0
MIN_TORSO_PX = 1.0
MIN_DROP_DT_S = 0.1


def _pair_point(kps: np.ndarray, a: int, b: int) -> tuple[np.ndarray, float]:
    """Middle of a left/right joint pair, using only the visible side when the other
    is hidden (side-on, or blocked by another person). Returns (point, confidence)."""
    visible = [i for i in (a, b) if kps[i, 2] >= JOINT_MIN_CONF] or [a, b]
    return kps[visible, :2].mean(axis=0), float(kps[[a, b], 2].max())


def _body_scale(kps: np.ndarray, shoulder_mid: np.ndarray, torso_length: float, bbox_diagonal: float) -> float:
    ankles = [i for i in (L_ANKLE, R_ANKLE) if kps[i, 2] >= ANKLE_MIN_CONF]
    if ankles:
        ankle_point = kps[ankles, :2].mean(axis=0)
        measured = float(np.linalg.norm(shoulder_mid - ankle_point))
    else:
        measured = TORSO_TO_BODY_RATIO * torso_length
    # A body can't be bigger than its own box; a stray keypoint can make it look so.
    return min(max(measured, MIN_BODY_TO_TORSO_RATIO * torso_length), bbox_diagonal)


def compute_features(person: PersonPose) -> PoseFeatures | None:
    """Return PoseFeatures, or None when the pose is too degenerate to measure."""
    kps = person.keypoints
    shoulder_mid, shoulder_conf = _pair_point(kps, L_SHOULDER, R_SHOULDER)
    hip_mid, hip_conf = _pair_point(kps, L_HIP, R_HIP)

    torso = shoulder_mid - hip_mid
    torso_length = float(np.linalg.norm(torso))
    if torso_length < MIN_TORSO_PX:
        return None

    # Image y grows downward, so an upright torso has torso[1] < 0 -> 0 degrees.
    torso_angle_deg = math.degrees(math.atan2(abs(torso[0]), -torso[1]))

    x1, y1, x2, y2 = person.bbox
    bbox_aspect = (x2 - x1) / max(y2 - y1, 1.0)
    bbox_diagonal = math.hypot(x2 - x1, y2 - y1)

    # Needs at least one reliable shoulder AND one reliable hip; unreliable ones are
    # already left out of the points above, so they can't bend the torso angle.
    keypoint_conf = min(shoulder_conf, hip_conf)

    return PoseFeatures(
        torso_angle_deg=torso_angle_deg,
        bbox_aspect=float(bbox_aspect),
        body_scale=_body_scale(kps, shoulder_mid, torso_length, bbox_diagonal),
        hip_y=float(hip_mid[1]),
        keypoint_conf=keypoint_conf,
    )


def drop_velocity(
    samples: Iterable[tuple[float, PoseFeatures]], now: float, current: PoseFeatures, window_s: float
) -> float:
    """Downward hip speed in body-heights / second over the last `window_s` seconds.

    `samples` are earlier (timestamp, PoseFeatures) pairs for the same track,
    oldest first. The oldest sample inside the window is the reference, and its
    body_scale is used because it was taken before the person went down.
    Upward movement returns 0.
    """
    reference = next(((t, f) for t, f in samples if now - t <= window_s), None)
    if reference is None:
        return 0.0
    ref_t, ref = reference
    dt = now - ref_t
    if dt < MIN_DROP_DT_S:
        return 0.0
    drop = (current.hip_y - ref.hip_y) / ref.body_scale
    return max(drop, 0.0) / dt
