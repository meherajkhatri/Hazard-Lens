from pathlib import Path

import cv2

try:
    from ultralytics import YOLO
except Exception:  # pragma: no cover - stub fallback when dependency unavailable
    YOLO = None


class PoseTracker:
    """Basic pose-tracking stub to bootstrap CV pipeline integration."""

    def __init__(self, model_path: str = "yolov8n-pose.pt") -> None:
        self.model_path = model_path
        self.model = YOLO(model_path) if YOLO else None

    def process_frame(self, frame) -> dict[str, object]:
        if frame is None:
            return {"status": "no_frame", "people_detected": 0, "poses": []}

        if self.model is None:
            return {
                "status": "model_unavailable",
                "people_detected": 0,
                "poses": [],
            }

        results = self.model(frame, verbose=False)
        people = int(len(results[0].keypoints)) if results and results[0].keypoints is not None else 0
        return {"status": "ok", "people_detected": people, "poses": []}

    def process_video(self, video_path: str) -> dict[str, object]:
        if not Path(video_path).exists():
            return {"status": "missing_video", "frames_processed": 0}

        capture = cv2.VideoCapture(video_path)
        frames_processed = 0

        while capture.isOpened():
            ok, frame = capture.read()
            if not ok:
                break
            self.process_frame(frame)
            frames_processed += 1

        capture.release()
        return {"status": "ok", "frames_processed": frames_processed}
