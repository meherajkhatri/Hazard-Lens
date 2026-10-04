"""Multi-person scenarios from live testing: several people in frame, people
hidden behind each other, tracker ID changes. Falls must be caught for
everyone; ordinary movement must not alert."""

import pytest

from cv_engine.detector.fall_state import FallDetector
from cv_engine.detector.types import L_HIP, L_SHOULDER, R_HIP, R_SHOULDER, FallState
from cv_engine.tests.synthetic import BODY_PX, make_pose

FPS = 30
STAND, FLOOR = 400.0, 400.0 + 0.5 * BODY_PX


def person(t, track, x, fall_at=None, hidden=None, lie_seconds=0.4):
    """Standing at hip_x=x; if fall_at is set, goes down over `lie_seconds` from then.
    `hidden=(t0, t1)`: joints unusable (blocked by someone) during that time."""
    k = 0.0 if fall_at is None else min(max((t - fall_at) / lie_seconds, 0.0), 1.0)
    p = make_pose(track, hip_y=STAND + (FLOOR - STAND) * k, angle_deg=85 * k, hip_x=x)
    if hidden and hidden[0] <= t < hidden[1]:
        p.keypoints[:, 2] = 0.1
    return p


def run(scene, seconds=8.0):
    detector, events = FallDetector(), []
    for i in range(int(seconds * FPS)):
        t = i / FPS
        events += detector.update(scene(t), t)
    return detector, events


def ids(events):
    return sorted(e.track_id for e in events)


# --- falls that must be caught -------------------------------------------------

def test_one_of_three_falls():
    _, events = run(lambda t: [person(t, 1, 100), person(t, 2, 320, fall_at=1.0), person(t, 3, 540)])
    assert ids(events) == [2]


def test_two_fall_at_the_same_time():
    _, events = run(lambda t: [person(t, 1, 150, fall_at=1.0), person(t, 2, 500, fall_at=1.0)])
    assert ids(events) == [1, 2]


def test_three_fall_a_moment_apart():
    _, events = run(lambda t: [person(t, 1, 100, fall_at=1.0), person(t, 2, 320, fall_at=1.3),
                               person(t, 3, 540, fall_at=1.6)])
    assert ids(events) == [1, 2, 3]


def test_faller_hidden_behind_someone_during_the_drop():
    _, events = run(lambda t: [person(t, 1, 320, fall_at=1.0, hidden=(0.9, 1.6)), person(t, 2, 360)])
    assert ids(events) == [1] and events[0].detection == "unseen_drop"


def test_tracker_gives_the_faller_a_new_id_right_after_landing():
    _, events = run(lambda t: [person(t, 1 if t < 1.5 else 7, 320, fall_at=1.0), person(t, 2, 100)])
    assert ids(events) == [7] and events[0].detection == "seen_drop"


def test_side_on_falls_with_far_side_hidden():
    def scene(t):
        a, b = person(t, 1, 150, fall_at=1.0), person(t, 2, 500, fall_at=1.0)
        a.keypoints[[R_SHOULDER, R_HIP], 2] = 0.0
        b.keypoints[[L_SHOULDER, L_HIP], 2] = 0.0
        return [a, b]
    _, events = run(scene)
    assert ids(events) == [1, 2]


# --- ordinary movement that must NOT alert -------------------------------------

def test_slow_lie_down_with_a_brief_occlusion():
    def scene(t):
        k = min(t / 4.0, 1.0)
        p = make_pose(1, hip_y=STAND + (FLOOR - STAND) * k, angle_deg=88 * k)
        if 1.5 <= t < 2.0:
            p.keypoints[:, 2] = 0.1
        return [p]
    _, events = run(scene, seconds=7.0)
    assert events == []


def test_hidden_then_reappearing_standing():
    _, events = run(lambda t: [person(t, 1, 320, hidden=(1.0, 2.0)), person(t, 2, 360)])
    assert events == []


def test_two_people_cross_and_swap_ids():
    def scene(t):
        x1, x2 = 100 + 60 * t, 500 - 60 * t
        swap = t >= 3.3
        return [make_pose(2 if swap else 1, hip_x=x1), make_pose(1 if swap else 2, hip_x=x2)]
    _, events = run(scene)
    assert events == []


def test_someone_walks_into_the_spot_a_lost_person_left():
    def scene(t):
        if t < 2.0:
            return [person(t, 1, 320)]
        return [person(t, 5, 330)] if t >= 2.5 else []
    detector, events = run(scene)
    assert events == [] and detector.state_of(5) is FallState.UPRIGHT


def test_reported_person_given_a_new_id_on_the_floor_gets_no_second_alert():
    _, events = run(lambda t: [person(t, 1 if t < 4.0 else 9, 320, fall_at=1.0)])
    assert ids(events) == [1]


# --- found_down: lying a long time, no fall seen --------------------------------

def lying_from_start(t, track=1, x=320):
    return make_pose(track, hip_y=FLOOR, angle_deg=85, hip_x=x)


def test_person_already_on_the_floor_is_reported_after_found_down_time():
    from cv_engine.config import FallThresholds

    th = FallThresholds()
    detector, events = run(lambda t: [lying_from_start(t)], seconds=th.FOUND_DOWN_S + 1)
    [event] = events
    assert event.detection == "found_down"
    assert event.timestamp == pytest.approx(th.FOUND_DOWN_S, abs=0.1)
    assert event.pose_confidence >= 0.7  # clears the backend's MIN_CONFIDENCE
    assert detector.state_of(1) is FallState.DOWN


def test_found_down_is_followed_up_like_any_fall():
    from cv_engine.detector.types import Assessment

    detector, events = run(lambda t: [lying_from_start(t)], seconds=22)
    assert len(events) == 1
    assert [a.outcome for a in detector.pop_assessments()] == [Assessment.UNRESPONSIVE]


def test_on_floor_counter_runs_then_stops_when_they_get_up():
    detector = FallDetector()
    for i in range(int(5 * FPS)):
        detector.update([lying_from_start(i / FPS)], i / FPS)
    assert detector.lying_seconds(1, 5.0) == pytest.approx(5.0, abs=0.1)
    for i in range(int(5 * FPS), int(7 * FPS)):
        detector.update([make_pose(1, hip_y=STAND)], i / FPS)
    assert detector.lying_seconds(1, 7.0) is None


def test_getting_up_before_found_down_time_sends_nothing():
    _, events = run(lambda t: [lying_from_start(t) if t < 8 else make_pose(1, hip_y=STAND)], seconds=14)
    assert events == []


def test_seen_fall_is_not_reported_twice_by_found_down():
    _, events = run(lambda t: [person(t, 1, 320, fall_at=1.0)], seconds=25)
    assert [e.detection for e in events] == ["seen_drop"]


def test_slow_deliberate_lie_down_is_flagged_only_after_found_down_time():
    """By design: not a fall alert, but someone lying 10s+ in the area is reported."""
    def scene(t):
        k = min(t / 4.0, 1.0)
        return [make_pose(1, hip_y=STAND + (FLOOR - STAND) * k, angle_deg=88 * k)]
    _, early = run(scene, seconds=7.0)
    assert early == []
    _, late = run(scene, seconds=16.0)
    assert [e.detection for e in late] == ["found_down"]
