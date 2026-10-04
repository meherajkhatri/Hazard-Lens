"""PoseEstimator: YOLOv8-pose + ByteTrack -> list[PersonPose] per frame."""

from pathlib import Path

import numpy as np

from cv_engine.detector.types import PersonPose


# Tuned for people lying down or partly hidden, who score lower than people standing.
TRACKER_CONFIG = Path(__file__).with_name("bytetrack.yaml")
# Ultralytics default is 0.25; lying people often score 0.15-0.45.
DETECTION_CONF = 0.15


def parse_result(result) -> list[PersonPose]:
    """Convert one Ultralytics Results object into PersonPose objects.

    Detections without a track ID (the tracker hasn't confirmed them yet) are
    dropped, because FallDetector needs a stable track_id per person.
    """
    boxes, keypoints = result.boxes, result.keypoints
    if boxes is None or keypoints is None or boxes.id is None or len(boxes) == 0:
        return []

    ids = boxes.id.int().cpu().numpy()
    xyxy = boxes.xyxy.cpu().numpy()
    kps = keypoints.data.cpu().numpy().astype(float)  # (N, 17, 3): x, y, conf
    # Ultralytics moves keypoints it considers not visible to (0, 0) but keeps
    # their confidence (often 0.3-0.5). Zero it so nothing downstream trusts them.
    hidden = (kps[..., 0] == 0) & (kps[..., 1] == 0)
    kps[hidden, 2] = 0.0
    return [
        PersonPose(
            track_id=int(track_id),
            keypoints=kps[i],
            bbox=tuple(float(v) for v in xyxy[i]),
        )
        for i, track_id in enumerate(ids)
    ]


class PoseEstimator:
    def __init__(self, model_path: str = "yolov8n-pose.pt", device: str = "cpu", imgsz: int = 640) -> None:
        # Imported here so tests and the rest of the engine don't need torch.
        from ultralytics import YOLO

        self.model = YOLO(model_path)
        self.device = device
        self.imgsz = imgsz

    def __call__(self, frame: np.ndarray) -> list[PersonPose]:
        results = self.model.track(
            frame,
            persist=True,
            tracker=str(TRACKER_CONFIG),
            conf=DETECTION_CONF,
            classes=[0],
            device=self.device,
            imgsz=self.imgsz,
            verbose=False,
        )
        return parse_result(results[0]) if results else []

    def reset_tracking(self) -> None:
        """Forget all tracks, e.g. between two unrelated clips."""
        predictor = getattr(self.model, "predictor", None)
        for tracker in getattr(predictor, "trackers", None) or []:
            tracker.reset()

    def warmup(self, frames: int = 10, shape: tuple[int, int] = (480, 640)) -> None:
        """Run blank frames so the first real inference isn't 2-5s slow on stage.

        Uses predict, not track, so warm-up frames don't create tracker state.
        """
        blank = np.zeros((*shape, 3), dtype=np.uint8)
        for _ in range(frames):
            self.model.predict(blank, device=self.device, imgsz=self.imgsz, verbose=False)
