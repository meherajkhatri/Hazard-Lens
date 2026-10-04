"""FallDetector: one UPRIGHT -> FALLING -> DOWN state machine per track_id.

See docs/dev1-cv-engine-plan.md section 3 for the transition rules. Every
threshold comes from FallThresholds so it can be tuned without code changes.
"""

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from cv_engine.config import FallThresholds
from cv_engine.detector.features import compute_features, drop_velocity
from cv_engine.detector.types import (
    Assessment,
    FallEvent,
    FallState,
    PersonPose,
    PoseFeatures,
    PostFallAssessment,
)

# Joints counted for the post-fall stillness check.
MOTION_MIN_CONF = 0.3
# Cap on keypoint samples kept while a person is down (about 20s at 30 FPS).
MAX_DOWN_SAMPLES = 600
# How fast the standing-height reference follows a person who moves nearer or further.
STANDING_HEIGHT_ALPHA = 0.05


def bbox_height(person: PersonPose) -> float:
    return max(person.bbox[3] - person.bbox[1], 1.0)


@dataclass
class _Track:
    last_seen: float
    state: FallState = FallState.UPRIGHT
    history: deque[tuple[float, PoseFeatures]] = field(default_factory=deque)
    drop_started_at: float | None = None
    peak_drop_velocity: float = 0.0
    horizontal_since: float | None = None
    upright_since: float | None = None
    last_event_at: float | None = None
    # Post-fall check: the fall being followed up, when DOWN started, and the
    # keypoints seen since then.
    fall: FallEvent | None = None
    down_since: float | None = None
    down_keypoints: list = field(default_factory=list)
    down_scale: float = 0.0
    outcome: Assessment | None = None
    # Box height while standing, learned in UPRIGHT; None until first seen upright.
    standing_height: float | None = None


def joint_spread(samples: list, body_scale: float) -> float:
    """How much the joints moved while down, in body-heights.

    Per joint, the standard deviation of its position over all samples, then the
    mean over joints that were confidently visible throughout. Using spread
    over the whole window rather than frame-to-frame speed keeps the model's
    1-3 px jitter from looking like movement.
    """
    if len(samples) < 2 or body_scale <= 0:
        return 0.0
    kps = np.stack(samples)  # (frames, 17, 3)
    visible = (kps[..., 2] >= MOTION_MIN_CONF).all(axis=0)
    if not visible.any():
        return 0.0
    xy = kps[:, visible, :2]
    return float(np.linalg.norm(xy.std(axis=0), axis=1).mean() / body_scale)

# Every FallEvent has already passed the state machine, so its score starts at
# CONFIRMED_FALL_BASE and the features only say how clean the fall was. With the
# default FallThresholds the weakest possible confirmed fall scores ~0.736,
# above the backend's MIN_CONFIDENCE of 0.7.
CONFIRMED_FALL_BASE = 0.65
MANUAL_CONFIDENCE = 1.0


def fall_quality(features: PoseFeatures, peak_drop_velocity: float, collapse: float = 0.0) -> float:
    """`collapse` is 1 - height / standing height: a person lying toward the camera
    scores on collapse instead of torso angle."""
    lying = max(min(features.torso_angle_deg / 90.0, 1.0), min(collapse / 0.5, 1.0))
    signal = (
        0.4 * lying
        + 0.3 * min(features.bbox_aspect / 1.5, 1.0)
        + 0.3 * min(peak_drop_velocity / 1.0, 1.0)
    )
    return max(0.0, min(signal * features.keypoint_conf, 1.0))


def pose_confidence(features: PoseFeatures, peak_drop_velocity: float, collapse: float = 0.0) -> float:
    return CONFIRMED_FALL_BASE + (1.0 - CONFIRMED_FALL_BASE) * fall_quality(features, peak_drop_velocity, collapse)


class FallDetector:
    def __init__(self, thresholds: FallThresholds | None = None) -> None:
        self.thresholds = thresholds or FallThresholds()
        self._tracks: dict[int, _Track] = {}
        self._assessments: list[PostFallAssessment] = []

    def pop_assessments(self) -> list[PostFallAssessment]:
        """Post-fall judgements made since the last call."""
        out, self._assessments = self._assessments, []
        return out

    def down_status(self, track_id: int, now: float) -> tuple[float, Assessment | None] | None:
        """(seconds down, outcome so far) for a person who is DOWN after a FallEvent."""
        track = self._tracks.get(track_id)
        if not track or track.state is not FallState.DOWN or track.down_since is None:
            return None
        return now - track.down_since, track.outcome

    def _assess(self, track: _Track, outcome: Assessment, now: float) -> None:
        motion = joint_spread(track.down_keypoints, track.down_scale)
        track.outcome = outcome
        self._assessments.append(PostFallAssessment(
            fall=track.fall, outcome=outcome, timestamp=now,
            seconds_down=now - track.down_since, motion=motion))

    def state_of(self, track_id: int) -> FallState:
        track = self._tracks.get(track_id)
        return track.state if track else FallState.UPRIGHT

    def force_event(self, person: PersonPose, now: float) -> FallEvent | None:
        """Manual trigger (F key) for the demo. Marks the person DOWN and returns
        a FallEvent flagged manual=True, or None if the pose can't be measured."""
        features = compute_features(person)
        if features is None:
            return None
        track = self._tracks.setdefault(person.track_id, _Track(last_seen=now))
        track.state = FallState.DOWN
        track.upright_since = None
        track.last_event_at = now
        self._start_down(track, person, features, now)
        track.fall = FallEvent(
            track_id=person.track_id,
            timestamp=now,
            drop_started_at=now,
            pose_confidence=MANUAL_CONFIDENCE,
            torso_angle_deg=features.torso_angle_deg,
            bbox_aspect=features.bbox_aspect,
            drop_velocity=0.0,
            keypoint_conf=features.keypoint_conf,
            bbox=person.bbox,
            manual=True,
        )
        return track.fall

    def update(self, people: list[PersonPose], now: float) -> list[FallEvent]:
        """Feed one frame. Returns the FallEvents confirmed on this frame."""
        events: list[FallEvent] = []
        for person in people:
            track = self._tracks.setdefault(person.track_id, _Track(last_seen=now))
            track.last_seen = now
            features = compute_features(person)
            if features is None or features.keypoint_conf < self.thresholds.MIN_KEYPOINT_CONF:
                continue
            event = self._step(person, track, features, now)
            if event:
                events.append(event)

        ttl = self.thresholds.TRACK_TTL_S
        self._tracks = {tid: t for tid, t in self._tracks.items() if now - t.last_seen <= ttl}
        return events

    def _step(
        self, person: PersonPose, track: _Track, features: PoseFeatures, now: float
    ) -> FallEvent | None:
        th = self.thresholds
        velocity = drop_velocity(track.history, now, features, th.FALL_DROP_WINDOW_S)
        track.history.append((now, features))
        while track.history and now - track.history[0][0] > th.FALL_DROP_WINDOW_S:
            track.history.popleft()

        height = bbox_height(person)
        collapse = 1.0 - height / track.standing_height if track.standing_height else 0.0

        if track.state is FallState.UPRIGHT:
            if velocity >= th.FALL_DROP_VELOCITY:
                track.state = FallState.FALLING
                track.drop_started_at = now
                track.peak_drop_velocity = velocity
                track.horizontal_since = None
            elif track.standing_height is None:
                track.standing_height = height
            else:
                track.standing_height += STANDING_HEIGHT_ALPHA * (height - track.standing_height)
            return None

        if track.state is FallState.FALLING:
            track.peak_drop_velocity = max(track.peak_drop_velocity, velocity)
            horizontal = (
                features.torso_angle_deg >= th.DOWN_TORSO_MIN_DEG
                and features.bbox_aspect >= th.DOWN_ASPECT_MIN
            )
            collapsed = collapse >= 1.0 - th.COLLAPSE_HEIGHT_RATIO
            if not (horizontal or collapsed):
                track.horizontal_since = None
                if now - track.drop_started_at > th.FALLING_TIMEOUT_S:
                    track.state = FallState.UPRIGHT
                return None

            if track.horizontal_since is None:
                track.horizontal_since = now
            if now - track.horizontal_since < th.DOWN_CONFIRM_S:
                return None

            track.state = FallState.DOWN
            track.upright_since = None
            self._start_down(track, person, features, now)
            if track.last_event_at is not None and now - track.last_event_at < th.EVENT_COOLDOWN_S:
                return None
            track.last_event_at = now
            track.fall = FallEvent(
                track_id=person.track_id,
                timestamp=now,
                drop_started_at=track.drop_started_at,
                pose_confidence=pose_confidence(features, track.peak_drop_velocity, collapse),
                torso_angle_deg=features.torso_angle_deg,
                bbox_aspect=features.bbox_aspect,
                drop_velocity=track.peak_drop_velocity,
                keypoint_conf=features.keypoint_conf,
                bbox=person.bbox,
            )
            return track.fall

        # DOWN: follow up on the fall, and wait for a sustained return to upright.
        # Height must come back too: someone lying toward the camera has an
        # upright-looking torso the whole time.
        height_back = track.standing_height is None or height >= th.RECOVER_HEIGHT_RATIO * track.standing_height
        if features.torso_angle_deg <= th.UPRIGHT_TORSO_MAX_DEG and height_back:
            if track.upright_since is None:
                track.upright_since = now
            if now - track.upright_since >= th.RECOVER_CONFIRM_S:
                if track.fall is not None and track.outcome is not Assessment.RECOVERED:
                    self._assess(track, Assessment.RECOVERED, now)
                track.state = FallState.UPRIGHT
                track.drop_started_at = None
                track.peak_drop_velocity = 0.0
                track.fall = None
                track.down_since = None
                track.down_keypoints = []
                track.outcome = None
            return None

        track.upright_since = None
        if len(track.down_keypoints) < MAX_DOWN_SAMPLES:
            track.down_keypoints.append(person.keypoints)
        if track.fall is not None and track.outcome is None and now - track.down_since >= th.ASSESS_AFTER_S:
            still = joint_spread(track.down_keypoints, track.down_scale) <= th.STILL_SPREAD_MAX
            self._assess(track, Assessment.UNRESPONSIVE if still else Assessment.MOVING, now)
        return None

    @staticmethod
    def _start_down(track: _Track, person: PersonPose, features: PoseFeatures, now: float) -> None:
        track.fall = None
        track.down_since = now
        track.down_keypoints = [person.keypoints]
        track.down_scale = features.body_scale
        track.outcome = None
