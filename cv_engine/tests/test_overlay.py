import numpy as np

from cv_engine.detector.types import FallState
from cv_engine.overlay import STATE_COLORS, draw_frame
from cv_engine.tests.synthetic import make_pose

FRAME = np.full((720, 640, 3), 128, dtype=np.uint8)


def _has_color(img, bgr):
    return bool(np.all(img == np.array(bgr, dtype=np.uint8), axis=-1).any())


def test_draws_box_in_state_color_without_touching_input():
    original = FRAME.copy()
    out = draw_frame(FRAME, [make_pose(track_id=3)], {3: FallState.FALLING}, "Zone 1")
    assert np.array_equal(FRAME, original)
    assert out.shape == FRAME.shape
    assert _has_color(out, STATE_COLORS[FallState.FALLING])
    assert not _has_color(out, STATE_COLORS[FallState.DOWN])


def test_down_state_adds_red_alert_border():
    out = draw_frame(FRAME, [make_pose(track_id=1, angle_deg=85)], {1: FallState.DOWN}, "Zone 1")
    assert tuple(out[-1, 0]) == STATE_COLORS[FallState.DOWN]


def test_skeleton_only_hides_the_camera_image():
    out = draw_frame(FRAME, [make_pose()], {}, "Zone 1", skeleton_only=True)
    assert not _has_color(out, (128, 128, 128))
    assert _has_color(out, STATE_COLORS[FallState.UPRIGHT])
