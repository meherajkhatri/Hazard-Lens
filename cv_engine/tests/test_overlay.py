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


def test_vision_warning_adds_amber_bar_at_bottom():
    from cv_engine.overlay import VISION_WARNING_COLOR

    out = draw_frame(FRAME, [], {}, "Zone 1", vision_warning="VISION IMPAIRED: GLARE")
    assert tuple(out[-3, 2]) == VISION_WARNING_COLOR
    assert not _has_color(draw_frame(FRAME, [], {}, "Zone 1"), VISION_WARNING_COLOR)


def test_long_banner_text_stays_inside_a_640px_frame():
    from cv_engine.overlay import BANNER_PX

    frame = np.zeros((480, 640, 3), np.uint8)
    long_status = "NO MOVEMENT - POSSIBLE MEDICAL EMERGENCY  |  Forklift Corridor | corridor-cam-1 | 24 FPS | 3 people"
    out = draw_frame(frame, [], {}, long_status)
    banner = out[:BANNER_PX]
    text_cols = np.where((banner == 255).all(axis=-1).any(axis=0))[0]
    assert text_cols.max() < 640 - 4  # last glyph ends before the right edge
