"""Scenario tests for FallDetector, played back at 30 FPS on synthetic poses."""

import pytest

from cv_engine.config import FallThresholds
from cv_engine.detector.fall_state import FallDetector
from cv_engine.detector.types import FallState
from cv_engine.tests.synthetic import BODY_PX, make_pose

FPS = 30
STAND_HIP_Y = 400.0
FLOOR_HIP_Y = STAND_HIP_Y + 0.5 * BODY_PX


class Scene:
    """Moves one person through keyframes and records every FallEvent."""

    def __init__(self, detector: FallDetector | None = None, track_id: int = 1) -> None:
        self.detector = detector or FallDetector()
        self.track_id = track_id
        self.t = 0.0
        self.hip_y = STAND_HIP_Y
        self.angle = 0.0
        self.squash = 1.0
        self.events = []

    def move(self, seconds: float, hip_y: float | None = None, angle: float | None = None, **pose_kw):
        """Linearly move to (hip_y, angle) over `seconds`, one update per frame."""
        start_y, start_a = self.hip_y, self.angle
        end_y = start_y if hip_y is None else hip_y
        end_a = start_a if angle is None else angle
        frames = max(1, round(seconds * FPS))
        for i in range(1, frames + 1):
            k = i / frames
            self.hip_y = start_y + (end_y - start_y) * k
            self.angle = start_a + (end_a - start_a) * k
            self.t += 1 / FPS
            pose = make_pose(self.track_id, hip_y=self.hip_y, angle_deg=self.angle, **pose_kw)
            self.events += self.detector.update([pose], self.t)
        return self

    def hold(self, seconds: float, **pose_kw):
        return self.move(seconds, **pose_kw)

    @property
    def state(self) -> FallState:
        return self.detector.state_of(self.track_id)


def fall(scene: Scene) -> Scene:
    return scene.move(0.4, hip_y=FLOOR_HIP_Y, angle=85)


def get_up(scene: Scene) -> Scene:
    return scene.move(1.0, hip_y=STAND_HIP_Y, angle=0).hold(1.5)


def test_real_fall_emits_exactly_one_event():
    scene = fall(Scene().hold(1.0)).hold(5.0)
    assert len(scene.events) == 1
    assert scene.state is FallState.DOWN

    event = scene.events[0]
    assert event.track_id == 1
    assert 0.0 < event.pose_confidence <= 1.0
    assert event.drop_velocity >= FallThresholds().FALL_DROP_VELOCITY
    # Confirmed DOWN_CONFIRM_S after becoming horizontal: well under 2s after the drop.
    assert event.timestamp - event.drop_started_at < 2.0


def test_backward_fall_is_detected_too():
    scene = Scene().hold(1.0).move(0.4, hip_y=FLOOR_HIP_Y, angle=-85).hold(3.0)
    assert len(scene.events) == 1


def test_slow_lie_down_is_not_a_fall():
    scene = Scene().hold(1.0).move(4.0, hip_y=FLOOR_HIP_Y, angle=88).hold(3.0)
    assert scene.events == []
    assert scene.state is FallState.UPRIGHT


def test_fast_crouch_returns_to_upright_without_event():
    scene = Scene().hold(1.0).move(0.3, hip_y=STAND_HIP_Y + 0.35 * BODY_PX, angle=25).hold(3.0)
    assert scene.events == []
    assert scene.state is FallState.UPRIGHT


def test_dropping_into_a_chair_is_not_a_fall():
    scene = Scene().hold(1.0).move(0.4, hip_y=STAND_HIP_Y + 0.4 * BODY_PX, angle=10).hold(3.0)
    assert scene.events == []


def test_brief_horizontal_moment_is_not_confirmed():
    # Stumble: fast drop, nearly flat for half a second, then back up.
    scene = Scene().hold(1.0).move(0.3, hip_y=FLOOR_HIP_Y, angle=80).hold(0.5)
    get_up(scene)
    assert scene.events == []
    assert scene.state is FallState.UPRIGHT


def test_person_recovers_after_getting_up():
    scene = get_up(fall(Scene().hold(1.0)).hold(2.0))
    assert scene.state is FallState.UPRIGHT


def test_second_fall_within_cooldown_is_suppressed_then_allowed_after():
    scene = get_up(fall(Scene().hold(1.0)).hold(2.0))
    fall(scene.hold(1.0)).hold(2.0)
    assert len(scene.events) == 1
    assert scene.state is FallState.DOWN

    get_up(scene).hold(FallThresholds().EVENT_COOLDOWN_S)
    fall(scene).hold(2.0)
    assert len(scene.events) == 2


def test_low_confidence_frames_are_ignored():
    scene = fall(Scene().hold(1.0, conf=0.2)).hold(3.0, conf=0.2)
    assert scene.events == []


def test_new_track_id_while_on_the_floor_does_not_duplicate_alert():
    detector = FallDetector()
    first = fall(Scene(detector, track_id=1).hold(1.0)).hold(2.0)
    assert len(first.events) == 1

    # Tracker swaps the ID while the person lies still.
    second = Scene(detector, track_id=2)
    second.t, second.hip_y, second.angle = first.t, first.hip_y, first.angle
    second.hold(5.0)
    assert second.events == []


def test_two_people_are_tracked_independently():
    detector = FallDetector()
    t, events = 0.0, []
    for i in range(int(4 * FPS)):
        t += 1 / FPS
        falling_k = min(max((t - 1.0) / 0.4, 0.0), 1.0)
        faller = make_pose(1, hip_y=STAND_HIP_Y + 0.5 * BODY_PX * falling_k, angle_deg=85 * falling_k)
        bystander = make_pose(2, hip_x=100.0)
        events += detector.update([faller, bystander], t)
    assert [e.track_id for e in events] == [1]
    assert detector.state_of(2) is FallState.UPRIGHT


def test_tracks_are_forgotten_after_ttl():
    detector = FallDetector()
    fall(Scene(detector).hold(1.0)).hold(2.0)
    assert detector.state_of(1) is FallState.DOWN
    detector.update([], now=100.0)
    assert detector.state_of(1) is FallState.UPRIGHT


def test_force_event_marks_down_and_flags_manual():
    detector = FallDetector()
    event = detector.force_event(make_pose(track_id=4), now=10.0)
    assert event.manual and event.track_id == 4
    assert detector.state_of(4) is FallState.DOWN
    # A real fall right after doesn't double-alert: cooldown applies.
    scene = Scene(detector, track_id=4)
    scene.t = 10.0
    fall(get_up(scene)).hold(2.0)
    assert scene.events == []


def test_weakest_confirmable_fall_clears_backend_min_confidence():
    """Backend ignores pose_confidence < 0.7 (MIN_CONFIDENCE). A fall that only
    just meets every FallThresholds minimum must still clear it."""
    from cv_engine.detector.fall_state import pose_confidence
    from cv_engine.detector.types import PoseFeatures

    th = FallThresholds()
    weakest = PoseFeatures(torso_angle_deg=th.DOWN_TORSO_MIN_DEG, bbox_aspect=th.DOWN_ASPECT_MIN,
                           body_scale=300.0, hip_y=0.0, keypoint_conf=th.MIN_KEYPOINT_CONF)
    assert pose_confidence(weakest, th.FALL_DROP_VELOCITY) > 0.7
    assert pose_confidence(weakest, th.FALL_DROP_VELOCITY) == pytest.approx(0.736, abs=0.001)


def test_manual_event_has_full_confidence():
    assert FallDetector().force_event(make_pose(), now=1.0).pose_confidence == 1.0


# --- post-fall check ---------------------------------------------------------

import math

import numpy as np

from cv_engine.detector.fall_state import joint_spread
from cv_engine.detector.types import Assessment


def lie(scene: Scene, seconds: float, sway_px: float = 0.0, jitter_px: float = 2.0, seed: int = 0) -> Scene:
    """Hold the fallen pose: `sway_px` = deliberate movement, `jitter_px` = model noise."""
    rng = np.random.default_rng(seed)
    for i in range(int(seconds * FPS)):
        scene.t += 1 / FPS
        pose = make_pose(scene.track_id, hip_y=scene.hip_y, angle_deg=scene.angle,
                         hip_x=320 + sway_px * math.sin(scene.t * 4))
        pose.keypoints[:, :2] += rng.normal(0, jitter_px, (17, 2))
        scene.events += scene.detector.update([pose], scene.t)
    return scene


def test_still_after_fall_is_judged_unresponsive_once():
    scene = fall(Scene().hold(1.0))
    lie(scene, 14.0)
    [a] = scene.detector.pop_assessments()
    assert a.outcome is Assessment.UNRESPONSIVE
    assert a.fall is scene.events[0]
    assert a.seconds_down == pytest.approx(FallThresholds().ASSESS_AFTER_S, abs=0.1)
    assert a.motion < FallThresholds().STILL_SPREAD_MAX
    assert scene.detector.pop_assessments() == []  # judged once


def test_moving_on_the_floor_is_judged_moving():
    scene = lie(fall(Scene().hold(1.0)), 12.0, sway_px=40.0)
    [a] = scene.detector.pop_assessments()
    assert a.outcome is Assessment.MOVING and a.motion > FallThresholds().STILL_SPREAD_MAX


def test_getting_up_quickly_is_judged_recovered():
    scene = lie(fall(Scene().hold(1.0)), 3.0)
    get_up(scene)
    [a] = scene.detector.pop_assessments()
    assert a.outcome is Assessment.RECOVERED and a.seconds_down < 6


def test_unresponsive_person_who_gets_up_is_then_recovered():
    scene = lie(fall(Scene().hold(1.0)), 12.0)
    get_up(scene)
    outcomes = [a.outcome for a in scene.detector.pop_assessments()]
    assert outcomes == [Assessment.UNRESPONSIVE, Assessment.RECOVERED]


def test_down_status_counts_seconds_and_shows_outcome():
    scene = lie(fall(Scene().hold(1.0)), 4.0)
    seconds, outcome = scene.detector.down_status(1, scene.t)
    assert 2.5 <= seconds < 4.0 and outcome is None  # DOWN starts once the fall is confirmed
    lie(scene, 8.0)
    assert scene.detector.down_status(1, scene.t)[1] is Assessment.UNRESPONSIVE
    assert scene.detector.down_status(99, scene.t) is None


def test_no_follow_up_for_a_fall_suppressed_by_cooldown():
    scene = get_up(lie(fall(Scene().hold(1.0)), 2.0))
    scene.detector.pop_assessments()
    lie(fall(scene.hold(1.0)), 12.0)  # second fall inside EVENT_COOLDOWN_S: no event, no follow-up
    assert len(scene.events) == 1 and scene.detector.pop_assessments() == []


def test_manual_fall_is_followed_up_too():
    detector = FallDetector()
    detector.force_event(make_pose(track_id=5, angle_deg=85), now=0.0)
    scene = Scene(detector, track_id=5)
    scene.hip_y, scene.angle = 400.0, 85.0
    lie(scene, 11.0)
    [a] = detector.pop_assessments()
    assert a.outcome is Assessment.UNRESPONSIVE and a.fall.manual


def test_joint_spread_separates_jitter_from_movement():
    rng = np.random.default_rng(3)
    base = make_pose(angle_deg=85).keypoints
    jitter = [base + np.c_[rng.normal(0, 2, (17, 2)), np.zeros(17)] for _ in range(100)]
    moving = [base + np.c_[np.full((17, 2), 40 * math.sin(i / 5)), np.zeros(17)] for i in range(100)]
    assert joint_spread(jitter, 300.0) < 0.015 < 0.03 < joint_spread(moving, 300.0)


# --- lying toward the camera (foreshortened) ---------------------------------

def squash_move(scene: Scene, seconds: float, hip_y: float, angle: float, squash_from: float, squash_to: float):
    frames = max(1, round(seconds * FPS))
    y0, a0 = scene.hip_y, scene.angle
    for i in range(1, frames + 1):
        k = i / frames
        scene.hip_y, scene.angle = y0 + (hip_y - y0) * k, a0 + (angle - a0) * k
        scene.squash = squash_from + (squash_to - squash_from) * k
        scene.t += 1 / FPS
        pose = make_pose(scene.track_id, hip_y=scene.hip_y, angle_deg=scene.angle, squash=scene.squash)
        scene.events += scene.detector.update([pose], scene.t)
    return scene


def test_fall_toward_camera_is_confirmed_from_height_collapse():
    """Torso stays near vertical in the image, but the body shrinks to a third."""
    scene = Scene().hold(1.0)
    squash_move(scene, 0.4, hip_y=FLOOR_HIP_Y, angle=12, squash_from=1.0, squash_to=0.35)
    squash_move(scene, 3.0, hip_y=FLOOR_HIP_Y, angle=12, squash_from=0.35, squash_to=0.35)
    assert len(scene.events) == 1
    th = FallThresholds()
    # Neither old "horizontal" condition holds, so only the collapse check can confirm it.
    assert scene.events[0].torso_angle_deg < th.DOWN_TORSO_MIN_DEG and scene.events[0].bbox_aspect < th.DOWN_ASPECT_MIN
    assert scene.events[0].pose_confidence >= 0.7  # still clears the backend's MIN_CONFIDENCE
    assert scene.state is FallState.DOWN


def test_person_lying_toward_camera_is_not_mistaken_for_recovered():
    """Lying straight toward the camera: the image torso is near vertical (< 30 deg),
    which alone would read as 'back upright'. Only the height check keeps them DOWN."""
    scene = Scene().hold(1.0)
    squash_move(scene, 0.4, hip_y=FLOOR_HIP_Y, angle=12, squash_from=1.0, squash_to=0.35)
    squash_move(scene, 0.5, hip_y=FLOOR_HIP_Y, angle=4, squash_from=0.35, squash_to=0.35)
    squash_move(scene, 12.5, hip_y=FLOOR_HIP_Y, angle=4, squash_from=0.35, squash_to=0.35)
    from cv_engine.detector.features import compute_features
    lying = make_pose(1, hip_y=FLOOR_HIP_Y, angle_deg=4, squash=0.35)
    assert compute_features(lying).torso_angle_deg < FallThresholds().UPRIGHT_TORSO_MAX_DEG
    assert scene.state is FallState.DOWN
    assert [a.outcome for a in scene.detector.pop_assessments()] == [Assessment.UNRESPONSIVE]

    squash_move(scene, 1.0, hip_y=STAND_HIP_Y, angle=0, squash_from=0.35, squash_to=1.0)
    squash_move(scene, 1.5, hip_y=STAND_HIP_Y, angle=0, squash_from=1.0, squash_to=1.0)
    assert scene.state is FallState.UPRIGHT
    assert [a.outcome for a in scene.detector.pop_assessments()] == [Assessment.RECOVERED]


def test_fast_crouch_toward_camera_is_not_a_fall():
    """Crouching shrinks the body too, but not below half of standing height."""
    scene = Scene().hold(1.0)
    squash_move(scene, 0.3, hip_y=STAND_HIP_Y + 0.35 * BODY_PX, angle=20, squash_from=1.0, squash_to=0.65)
    squash_move(scene, 3.0, hip_y=STAND_HIP_Y + 0.35 * BODY_PX, angle=20, squash_from=0.65, squash_to=0.65)
    assert scene.events == []
    assert scene.state is FallState.UPRIGHT


def test_weakest_collapsed_fall_clears_backend_min_confidence():
    from cv_engine.detector.fall_state import pose_confidence
    from cv_engine.detector.types import PoseFeatures

    th = FallThresholds()
    upright_looking = PoseFeatures(torso_angle_deg=0.0, bbox_aspect=0.3, body_scale=300.0, hip_y=0.0,
                                   keypoint_conf=th.MIN_KEYPOINT_CONF)
    assert pose_confidence(upright_looking, th.FALL_DROP_VELOCITY, collapse=1 - th.COLLAPSE_HEIGHT_RATIO) > 0.7
