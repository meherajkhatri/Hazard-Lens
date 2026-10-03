"""Call-Help CV engine entrypoint.

    python -m cv_engine.run                      # webcam (CAMERA_INDEX)
    python -m cv_engine.run --video clip.mp4     # replay a recorded clip
    python -m cv_engine.run --video clip.mp4 --loop --skeleton-only

Keys in the preview window: q = quit, f = manual fall for the largest person.
"""

import argparse
import logging
import socket
import time

import cv2
import numpy as np

from cv_engine.config import EngineConfig
from cv_engine.detector.fall_state import FallDetector
from cv_engine.detector.types import FallEvent, PersonPose
from cv_engine.overlay import draw_frame
from cv_engine.transport.emitter import event_id, fall_payload, heartbeat_payload

log = logging.getLogger("cv_engine")
FPS_SMOOTHING = 0.9


def detect_public_host() -> str:
    """LAN IP other laptops can reach. No packet is sent by connecting UDP."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def largest_person(people: list[PersonPose]) -> PersonPose | None:
    def area(p: PersonPose) -> float:
        x1, y1, x2, y2 = p.bbox
        return (x2 - x1) * (y2 - y1)

    return max(people, key=area, default=None)


class Engine:
    """One frame in -> people detected, falls emitted, annotated frame out."""

    def __init__(self, cfg: EngineConfig, estimator, detector: FallDetector, emitter, streamer=None,
                 skeleton_only: bool = False, snapshot_base_url: str | None = None) -> None:
        self.cfg = cfg
        self.estimator = estimator
        self.detector = detector
        self.emitter = emitter
        self.streamer = streamer
        self.skeleton_only = skeleton_only
        self.snapshot_base_url = snapshot_base_url
        self.fps = 0.0
        self.people: list[PersonPose] = []
        self._last_frame_at: float | None = None
        self._last_heartbeat_at = float("-inf")

    def process(self, frame: np.ndarray, now: float, force_fall: bool = False) -> tuple[np.ndarray, list[FallEvent]]:
        """`now` is the frame's time: wall clock for a webcam, video time for a clip."""
        started = time.perf_counter()
        self.people = self.estimator(frame)
        events = self.detector.update(self.people, now)
        if force_fall and (target := largest_person(self.people)):
            if manual := self.detector.force_event(target, now):
                events.append(manual)

        if self._last_frame_at is not None and now > self._last_frame_at:
            instant = 1.0 / (now - self._last_frame_at)
            self.fps = instant if self.fps == 0 else FPS_SMOOTHING * self.fps + (1 - FPS_SMOOTHING) * instant
        self._last_frame_at = now

        states = {p.track_id: self.detector.state_of(p.track_id) for p in self.people}
        status = f"{self.cfg.ZONE_ID} | {self.cfg.CAMERA_ID} | {self.fps:.0f} FPS | {len(self.people)} people"
        annotated = draw_frame(frame, self.people, states, status, skeleton_only=self.skeleton_only)

        for event in events:
            # Same clock as `now`, plus the time this frame took to process.
            sent_at = now + (time.perf_counter() - started)
            if self.streamer:
                self.streamer.save_snapshot(event_id(self.cfg.CAMERA_ID, event), annotated)
            self.emitter.send(fall_payload(event, self.cfg.CAMERA_ID, self.cfg.ZONE_ID, sent_at, self.snapshot_base_url))
            log.warning("FALL track=%s conf=%.2f trigger=%s", event.track_id, event.pose_confidence,
                        "manual" if event.manual else "auto")

        if now - self._last_heartbeat_at >= self.cfg.HEARTBEAT_INTERVAL_S:
            self._last_heartbeat_at = now
            self.emitter.send(heartbeat_payload(self.cfg.CAMERA_ID, self.cfg.ZONE_ID, now, self.fps, len(self.people)))

        if self.streamer:
            self.streamer.status = {"fps": round(self.fps, 1), "people_detected": len(self.people)}
            self.streamer.update_frame(annotated)
        return annotated, events


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Call-Help CV engine")
    parser.add_argument("--video", help="replay a recorded clip instead of the webcam")
    parser.add_argument("--loop", action="store_true", help="restart the clip when it ends")
    parser.add_argument("--skeleton-only", action="store_true", help="privacy mode: never show or stream camera pixels")
    parser.add_argument("--no-window", action="store_true", help="don't open a preview window (headless)")
    parser.add_argument("--device", help="override DEVICE: cuda, mps or cpu")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    # Heavy imports stay here so `Engine` can be imported and tested without torch.
    from cv_engine.detector.pose import PoseEstimator
    from cv_engine.transport.emitter import TelemetryEmitter
    from cv_engine.transport.streamer import MjpegStreamer

    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = EngineConfig()
    device = args.device or cfg.DEVICE

    log.info("loading %s on %s", cfg.MODEL_PATH, device)
    estimator = PoseEstimator(cfg.MODEL_PATH, device=device)
    estimator.warmup()

    streamer = MjpegStreamer(port=cfg.STREAM_PORT).start()
    host = cfg.PUBLIC_HOST or detect_public_host()
    snapshot_base_url = f"http://{host}:{streamer.port}"
    emitter = TelemetryEmitter(cfg.BACKEND_URL, cfg.API_KEY)
    engine = Engine(cfg, estimator, FallDetector(cfg.thresholds), emitter, streamer,
                    skeleton_only=args.skeleton_only, snapshot_base_url=snapshot_base_url)
    log.info("stream: %s/stream   backend: %s", snapshot_base_url, cfg.BACKEND_URL)

    capture = cv2.VideoCapture(args.video if args.video else cfg.CAMERA_INDEX)
    if not capture.isOpened():
        raise SystemExit(f"could not open {'video ' + args.video if args.video else 'camera ' + str(cfg.CAMERA_INDEX)}")
    video_fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    clock_start, frame_index = time.time(), 0
    force_fall = False

    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                if args.video and args.loop:
                    capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                break
            # Replays use the clip's own timeline so a slow laptop doesn't
            # stretch a fall and hide its drop_velocity.
            now = clock_start + frame_index / video_fps if args.video else time.time()
            frame_index += 1

            annotated, _ = engine.process(frame, now, force_fall=force_fall)
            force_fall = False

            if not args.no_window:
                cv2.imshow("Call-Help CV engine", annotated)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                force_fall = key == ord("f")
    except KeyboardInterrupt:
        pass
    finally:
        capture.release()
        cv2.destroyAllWindows()
        emitter.close()
        streamer.stop()
        log.info("stopped; %d telemetry messages delivered, %d falls undelivered, %d falls rejected by backend",
                 emitter.delivered, emitter.pending_falls, emitter.rejected)


if __name__ == "__main__":
    main()
