"""VisionMonitor on a real photo with glare, darkness and smoke simulated on top."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from cv_engine.vision import BASELINE_SECONDS, CLEARED_AFTER_S, IMPAIRED_AFTER_S, VisionMonitor, measure

FPS = 15


@pytest.fixture(scope="module")
def scene() -> np.ndarray:
    try:
        import ultralytics

        img = cv2.imread(str(Path(ultralytics.__file__).parent / "assets" / "bus.jpg"))
        if img is not None:
            return cv2.resize(img, (640, 480))
    except ImportError:
        pass
    rng = np.random.default_rng(0)
    tiles = np.kron(rng.integers(40, 220, (12, 16)), np.ones((40, 40)))
    return np.dstack([tiles] * 3).astype(np.uint8)


def glare(img):
    out = img.copy()
    h, w = out.shape[:2]
    cv2.circle(out, (w // 2, h // 2), int(h * 0.42), (255, 255, 255), -1)  # flashlight into the lens
    return out


def dark(img):
    return (img * 0.05).astype(np.uint8)  # hand over the lens


def smoke(img):
    return cv2.addWeighted(img, 0.25, np.full_like(img, 170), 0.75, 0)  # thick haze


def play(monitor, frames, start=0.0):
    t = start
    for frame in frames:
        status = monitor.update(frame, t)
        t += 1 / FPS
    return status, t


def warm(monitor, scene):
    return play(monitor, [scene] * int((BASELINE_SECONDS + 0.5) * FPS))


def test_normal_scene_is_ok(scene):
    status, _ = warm(VisionMonitor(), scene)
    assert not status.impaired and status.label == "VISION OK"


@pytest.mark.parametrize("damage, reason", [(glare, "glare"), (dark, "dark"), (smoke, "haze")])
def test_each_problem_is_reported_after_it_persists(scene, damage, reason):
    monitor = VisionMonitor()
    _, t = warm(monitor, scene)
    bad = damage(scene)

    status, t = play(monitor, [bad] * int(IMPAIRED_AFTER_S * FPS * 0.5), t)
    assert not status.impaired  # a brief flash is ignored

    status, t = play(monitor, [bad] * int(IMPAIRED_AFTER_S * FPS + 2), t)
    assert status.impaired and status.reason == reason
    assert status.label == f"VISION IMPAIRED: {reason.upper()}"


def test_recovers_only_after_clear_view_holds(scene):
    monitor = VisionMonitor()
    _, t = warm(monitor, scene)
    _, t = play(monitor, [glare(scene)] * int(2 * FPS), t)
    status, t = play(monitor, [scene] * int(CLEARED_AFTER_S * FPS * 0.5), t)
    assert status.impaired  # not yet
    status, t = play(monitor, [scene] * int(CLEARED_AFTER_S * FPS + 2), t)
    assert not status.impaired


def test_plain_low_contrast_scene_is_not_smoke():
    """A camera that normally sees a plain wall must not report haze."""
    wall = np.full((480, 640, 3), 150, np.uint8)
    wall += np.random.default_rng(1).integers(0, 6, wall.shape, dtype=np.uint8)
    status, _ = play(VisionMonitor(), [wall] * int((BASELINE_SECONDS + 3) * FPS))
    assert not status.impaired


def test_smoke_does_not_teach_the_baseline(scene):
    """Contrast learned while impaired would make smoke look normal."""
    monitor = VisionMonitor()
    _, t = warm(monitor, scene)
    baseline = monitor._baseline_contrast
    play(monitor, [smoke(scene)] * int(20 * FPS), t)
    assert monitor._baseline_contrast == pytest.approx(baseline, rel=0.05)


def test_measure_reports_expected_metrics(scene):
    assert measure(glare(scene)).glare_fraction > 0.25
    assert measure(dark(scene)).brightness < 25
    assert measure(smoke(scene)).contrast < 0.4 * measure(scene).contrast
