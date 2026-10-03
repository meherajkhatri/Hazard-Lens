"""parse_result runs on fake Ultralytics output; the real-model test is skipped
unless ultralytics and the yolov8n-pose weights are available."""

from pathlib import Path

import numpy as np
import pytest

from cv_engine.detector.pose import parse_result


class _Tensor:
    def __init__(self, data):
        self._data = np.asarray(data)

    def int(self):
        return _Tensor(self._data.astype(int))

    def cpu(self):
        return self

    def numpy(self):
        return self._data


class _Boxes:
    def __init__(self, ids, xyxy):
        self.id = None if ids is None else _Tensor(ids)
        self.xyxy = _Tensor(xyxy)

    def __len__(self):
        return len(self.xyxy.numpy())


class _Keypoints:
    def __init__(self, data):
        self.data = _Tensor(data)


class _Result:
    def __init__(self, ids, n=2):
        self.boxes = _Boxes(ids, np.arange(n * 4, dtype=float).reshape(n, 4))
        self.keypoints = _Keypoints(np.random.rand(n, 17, 3))


def test_parse_result_builds_one_person_per_tracked_detection():
    people = parse_result(_Result(ids=[7.0, 9.0]))
    assert [p.track_id for p in people] == [7, 9]
    assert people[0].keypoints.shape == (17, 3)
    assert people[1].bbox == (4.0, 5.0, 6.0, 7.0)


def test_parse_result_drops_untracked_detections():
    assert parse_result(_Result(ids=None)) == []


def test_real_model_on_sample_image():
    ultralytics = pytest.importorskip("ultralytics")
    weights = Path("yolov8n-pose.pt")
    if not weights.exists():
        pytest.skip("yolov8n-pose.pt not downloaded")
    import cv2

    from cv_engine.detector.features import compute_features
    from cv_engine.detector.pose import PoseEstimator

    frame = cv2.imread(str(Path(ultralytics.__file__).parent / "assets" / "bus.jpg"))
    estimator = PoseEstimator(str(weights))
    estimator.warmup(frames=1)
    people = estimator(frame)
    assert people, "expected people in bus.jpg"
    # People standing in the photo should read as upright.
    upright = [f for f in map(compute_features, people) if f and f.keypoint_conf > 0.5]
    assert upright and all(f.torso_angle_deg < 30 for f in upright)
