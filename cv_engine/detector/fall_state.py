"""FallDetector: one UPRIGHT -> FALLING -> DOWN state machine per track_id.

See docs/dev1-cv-engine-plan.md section 3 for the transition rules. Every
threshold comes from FallThresholds so it can be tuned without code changes.
"""

from collections import deque
from dataclasses import dataclass, field

from cv_engine.config import FallThresholds
from cv_engine.detector.features import compute_features, drop_velocity
from cv_engine.detector.types import FallEvent, FallState, PersonPose, PoseFeatures


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


def pose_confidence(features: PoseFeatures, peak_drop_velocity: float) -> float:
    signal = (
        0.4 * min(features.torso_angle_deg / 90.0, 1.0)
        + 0.3 * min(features.bbox_aspect / 1.5, 1.0)
        + 0.3 * min(peak_drop_velocity / 1.0, 1.0)
    )
    return max(0.0, min(signal * features.keypoint_conf, 1.0))


class FallDetector:
    def __init__(self, thresholds: FallThresholds | None = None) -> None:
        self.thresholds = thresholds or FallThresholds()
        self._tracks: dict[int, _Track] = {}

    def state_of(self, track_id: int) -> FallState:
        track = self._tracks.get(track_id)
        return track.state if track else FallState.UPRIGHT

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

        if track.state is FallState.UPRIGHT:
            if velocity >= th.FALL_DROP_VELOCITY:
                track.state = FallState.FALLING
                track.drop_started_at = now
                track.peak_drop_velocity = velocity
                track.horizontal_since = None
            return None

        if track.state is FallState.FALLING:
            track.peak_drop_velocity = max(track.peak_drop_velocity, velocity)
            horizontal = (
                features.torso_angle_deg >= th.DOWN_TORSO_MIN_DEG
                and features.bbox_aspect >= th.DOWN_ASPECT_MIN
            )
            if not horizontal:
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
            if track.last_event_at is not None and now - track.last_event_at < th.EVENT_COOLDOWN_S:
                return None
            track.last_event_at = now
            return FallEvent(
                track_id=person.track_id,
                timestamp=now,
                drop_started_at=track.drop_started_at,
                pose_confidence=pose_confidence(features, track.peak_drop_velocity),
                torso_angle_deg=features.torso_angle_deg,
                bbox_aspect=features.bbox_aspect,
                drop_velocity=track.peak_drop_velocity,
                keypoint_conf=features.keypoint_conf,
                bbox=person.bbox,
            )

        # DOWN: wait for a sustained return to upright.
        if features.torso_angle_deg <= th.UPRIGHT_TORSO_MAX_DEG:
            if track.upright_since is None:
                track.upright_since = now
            if now - track.upright_since >= th.RECOVER_CONFIRM_S:
                track.state = FallState.UPRIGHT
                track.drop_started_at = None
                track.peak_drop_velocity = 0.0
        else:
            track.upright_since = None
        return None
