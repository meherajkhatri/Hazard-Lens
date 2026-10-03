"""eval_clips: labelling, scoring and sweep on scripted poses; extraction and
caching with the real model when the weights are available."""

import os
from pathlib import Path

import cv2
import numpy as np
import pytest

from cv_engine.config import FallThresholds
from cv_engine.eval_clips import (
    SWEEP_GRID,
    extract_poses,
    find_clips,
    is_fall_clip,
    main,
    score_all,
    summarize,
    sweep,
)
from cv_engine.tests.synthetic import BODY_PX, make_pose

FPS = 30


def scripted(seconds: float, pose_at) -> list:
    return [(i / FPS, pose_at(i / FPS)) for i in range(int(seconds * FPS))]


def fast_fall(t):
    k = min(max((t - 1.0) / 0.4, 0.0), 1.0)
    return [make_pose(1, hip_y=400 + 0.5 * BODY_PX * k, angle_deg=85 * k)]


def gentle_fall(t):
    """A real but slower fall: hips drop 50% of body height over 1.2s."""
    k = min(max((t - 1.0) / 1.2, 0.0), 1.0)
    return [make_pose(1, hip_y=400 + 0.5 * BODY_PX * k, angle_deg=85 * k)]


def slow_lie_down(t):
    k = min(t / 4.0, 1.0)
    return [make_pose(1, hip_y=400 + 0.5 * BODY_PX * k, angle_deg=88 * k)]


def crouch(t):
    k = min(max((t - 1.0) / 0.3, 0.0), 1.0)
    return [make_pose(1, hip_y=400 + 0.35 * BODY_PX * k, angle_deg=25 * k)]


CLIPS = {
    "fall_fast": (True, scripted(5, fast_fall)),
    "fall_gentle": (True, scripted(5, gentle_fall)),
    "adl_lie_down": (False, scripted(6, slow_lie_down)),
    "adl_crouch": (False, scripted(4, crouch)),
}


def test_labels_come_from_file_names():
    assert is_fall_clip(Path("fall_03.mp4")) and is_fall_clip(Path("Fall-01-cam0"))
    assert not is_fall_clip(Path("adl-01-cam0")) and not is_fall_clip(Path("sit_fall_nope.mp4"))


def test_default_thresholds_miss_the_gentle_fall():
    s = summarize(score_all(CLIPS, FallThresholds()))
    assert s == {"falls": 2, "caught": 1, "missed": 1, "non_falls": 2, "false_alarms": 0}


def test_sweep_finds_thresholds_that_catch_both_without_false_alarms():
    best, s = sweep(CLIPS, FallThresholds())[0]
    assert s["missed"] == 0 and s["false_alarms"] == 0
    assert best.FALL_DROP_VELOCITY < FallThresholds().FALL_DROP_VELOCITY
    assert set(SWEEP_GRID) <= set(vars(best))


def _write_video(path: Path, frames: int = 20):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), FPS, (320, 240))
    for i in range(frames):
        writer.write(np.full((240, 320, 3), i * 9 % 255, dtype=np.uint8))
    writer.release()


def test_find_clips_accepts_videos_and_frame_folders(tmp_path):
    _write_video(tmp_path / "fall_01.avi")
    frames = tmp_path / "adl-01-cam0-rgb"
    frames.mkdir()
    cv2.imwrite(str(frames / "0001.png"), np.zeros((10, 10, 3), np.uint8))
    (tmp_path / "notes.txt").write_text("ignored")
    (tmp_path / ".pose_cache").mkdir()
    assert [p.name for p in find_clips(tmp_path)] == ["adl-01-cam0-rgb", "fall_01.avi"]


WEIGHTS = Path(os.getenv("MODEL_PATH", "yolov8n-pose.pt"))


@pytest.mark.skipif(not WEIGHTS.exists(), reason="yolov8n-pose.pt not available")
def test_extraction_with_real_model_is_cached(tmp_path, monkeypatch, capsys):
    pytest.importorskip("ultralytics")
    from cv_engine.detector.pose import PoseEstimator

    clip = tmp_path / "fall_01.avi"
    _write_video(clip, frames=15)
    estimator = PoseEstimator(str(WEIGHTS))
    frames = extract_poses(clip, estimator, str(WEIGHTS))
    assert len(frames) == 15 and frames[1][0] == pytest.approx(1 / FPS)
    assert len(list((tmp_path / ".pose_cache").iterdir())) == 1

    # Second run must come from the cache, without the model.
    assert extract_poses(clip, None, str(WEIGHTS)) == frames

    monkeypatch.setenv("MODEL_PATH", str(WEIGHTS))
    from cv_engine import eval_clips
    monkeypatch.setattr(eval_clips, "EngineConfig", lambda: __import__("cv_engine.config").config.EngineConfig(MODEL_PATH=str(WEIGHTS)))
    main([str(tmp_path), "--sweep"])
    out = capsys.readouterr().out
    assert "falls caught 0/1" in out and "Top settings out of 108 combinations" in out


@pytest.mark.skipif(not WEIGHTS.exists(), reason="yolov8n-pose.pt not available")
def test_reset_tracking_restarts_track_ids():
    ultralytics = pytest.importorskip("ultralytics")
    from cv_engine.detector.pose import PoseEstimator

    image = cv2.imread(str(Path(ultralytics.__file__).parent / "assets" / "bus.jpg"))
    estimator = PoseEstimator(str(WEIGHTS))
    first = sorted(p.track_id for p in estimator(image))
    estimator.reset_tracking()
    assert sorted(p.track_id for p in estimator(image)) == first


def test_frame_folders_nested_one_level_are_found_and_read(tmp_path):
    from cv_engine.eval_clips import _read_frames, frame_dir

    outer = tmp_path / "fall-01-cam0-rgb"
    inner = outer / "fall-01-cam0-rgb"
    inner.mkdir(parents=True)
    for i in range(3):
        cv2.imwrite(str(inner / f"fall-01-cam0-rgb-{i:03d}.png"), np.full((10, 10, 3), i, np.uint8))
    (tmp_path / "empty-dir").mkdir()

    assert [p.name for p in find_clips(tmp_path)] == ["fall-01-cam0-rgb"]
    assert frame_dir(outer) == inner
    assert [round(t, 3) for t, _ in _read_frames(outer, 30.0)] == [0.0, 0.033, 0.067]
