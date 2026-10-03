import numpy as np
import pytest

from cv_engine.detector.features import compute_features, drop_velocity
from cv_engine.detector.types import L_ANKLE, R_ANKLE, R_SHOULDER, PersonPose
from cv_engine.tests.synthetic import BODY_PX, TORSO_PX, make_pose


def test_standing_person_is_upright_and_tall():
    f = compute_features(make_pose(angle_deg=0))
    assert f.torso_angle_deg == pytest.approx(0, abs=1)
    assert f.bbox_aspect < 0.6
    assert f.body_scale == pytest.approx(BODY_PX, rel=0.05)
    assert f.keypoint_conf == pytest.approx(0.9)


def test_lying_person_is_horizontal_and_wide():
    f = compute_features(make_pose(angle_deg=90))
    assert f.torso_angle_deg == pytest.approx(90, abs=1)
    assert f.bbox_aspect > 1.0


def test_torso_angle_ignores_left_right_direction():
    left = compute_features(make_pose(angle_deg=-75))
    right = compute_features(make_pose(angle_deg=75))
    assert left.torso_angle_deg == pytest.approx(right.torso_angle_deg, abs=0.5)


def test_body_scale_is_orientation_independent():
    standing = compute_features(make_pose(angle_deg=0))
    lying = compute_features(make_pose(angle_deg=90))
    assert lying.body_scale == pytest.approx(standing.body_scale, rel=0.05)


def test_body_scale_falls_back_to_torso_when_ankles_hidden():
    f = compute_features(make_pose(ankle_conf=0.0))
    assert f.body_scale == pytest.approx(3.0 * TORSO_PX, rel=0.05)


def test_degenerate_pose_returns_none():
    person = PersonPose(track_id=1, keypoints=np.zeros((17, 3)), bbox=(0, 0, 10, 10))
    assert compute_features(person) is None


def test_drop_velocity_measures_fast_hip_drop():
    start = compute_features(make_pose(hip_y=400))
    end = compute_features(make_pose(hip_y=400 + 0.3 * BODY_PX))  # 30% of body in 0.6s
    v = drop_velocity([(0.0, start)], now=0.6, current=end, window_s=0.6)
    assert v == pytest.approx(0.5, rel=0.05)


def test_drop_velocity_ignores_upward_movement_and_stale_samples():
    low = compute_features(make_pose(hip_y=500))
    high = compute_features(make_pose(hip_y=400))
    assert drop_velocity([(0.0, low)], now=0.5, current=high, window_s=0.6) == 0.0
    assert drop_velocity([(0.0, high)], now=2.0, current=low, window_s=0.6) == 0.0


def test_one_unreliable_joint_lowers_keypoint_conf():
    person = make_pose()
    person.keypoints[R_SHOULDER, 2] = 0.3
    assert compute_features(person).keypoint_conf == pytest.approx(0.3)


def test_body_scale_is_capped_by_bbox_diagonal():
    person = make_pose()
    person.keypoints[L_ANKLE, 1] += 5000  # stray ankle far outside the box
    person.keypoints[R_ANKLE, 1] += 5000
    x1, y1, x2, y2 = person.bbox
    assert compute_features(person).body_scale <= ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
