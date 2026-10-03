"""PoseEstimator: YOLOv8-pose + ByteTrack -> list[PersonPose] per frame."""

import numpy as np

from cv_engine.detector.types import PersonPose


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
    kps = keypoints.data.cpu().numpy()  # (N, 17, 3): x, y, conf
    return [
        PersonPose(
            track_id=int(track_id),
            keypoints=np.asarray(kps[i], dtype=float),
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
            tracker="bytetrack.yaml",
            classes=[0],
            device=self.device,
            imgsz=self.imgsz,
            verbose=False,
        )
        return parse_result(results[0]) if results else []

    def warmup(self, frames: int = 10, shape: tuple[int, int] = (480, 640)) -> None:
        """Run blank frames so the first real inference isn't 2-5s slow on stage.

        Uses predict, not track, so warm-up frames don't create tracker state.
        """
        blank = np.zeros((*shape, 3), dtype=np.uint8)
        for _ in range(frames):
            self.model.predict(blank, device=self.device, imgsz=self.imgsz, verbose=False)
