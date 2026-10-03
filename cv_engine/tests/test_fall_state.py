"""Scenario tests for FallDetector, played back at 30 FPS on synthetic poses."""

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
