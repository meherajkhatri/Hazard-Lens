"""Call-Help CV engine entrypoint.

    python -m cv_engine.run                      # webcam (CAMERA_INDEX)
    python -m cv_engine.run --video clip.mp4     # replay a recorded clip
    python -m cv_engine.run --video clip.mp4 --loop --skeleton-only
    python -m cv_engine.run --list-cameras       # which camera indexes work
    python -m cv_engine.run --camera-url http://192.168.1.23:8080/video   # phone camera app over Wi-Fi

Several cameras: one process per camera, each with its own id, index and port:
    python -m cv_engine.run --camera-id zone-1-cam-1 --zone-id "Zone 1" --camera-index 1 --port 8001
    python -m cv_engine.run --camera-id zone-1-cam-2 --zone-id "Zone 1" --camera-index 2 --port 8002

Keys in the preview window: q or Esc = quit, f = manual fall for the largest person.
Closing the preview window also stops the engine; so does Ctrl+C in the terminal.
"""

import argparse
import dataclasses
import json
import logging
import socket
import time

import cv2
import numpy as np

from cv_engine.camera import LiveCamera, list_cameras, open_camera, open_stream
from cv_engine.config import EngineConfig
from cv_engine.detector.fall_state import FallDetector
from cv_engine.detector.types import Assessment, FallEvent, PersonPose
from cv_engine.overlay import draw_frame
from cv_engine.transport.emitter import assessment_payload, event_id, fall_payload, heartbeat_payload
from cv_engine.vision import VisionMonitor

log = logging.getLogger("cv_engine")
FPS_SMOOTHING = 0.9
RECOVERED_LABEL_S = 5.0
OUTCOME_NOTES = {None: "", Assessment.UNRESPONSIVE: " - NO MOVEMENT", Assessment.MOVING: " - MOVING"}
UNRESPONSIVE_ALERT = "NO MOVEMENT - POSSIBLE MEDICAL EMERGENCY"


QUIT_KEYS = {ord("q"), ord("Q"), 27}  # q, Q, Esc


def window_closed(title: str) -> bool:
    """True once the user closed the preview window with its X button.

    Without this, imshow() reopens the window on the next frame and the engine
    keeps running with no visible way to stop it.
    """
    try:
        return cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE) < 1
    except cv2.error:
        return True


def usable_device(requested: str) -> str:
    """The requested device, or "cpu" with a warning if torch can't use it.

    A CPU-only PyTorch install (pip's default on Windows) otherwise crashes the
    engine at startup when DEVICE=cuda.
    """
    import torch

    if requested.startswith("cuda") and not torch.cuda.is_available():
        log.warning("DEVICE=%s but this PyTorch (%s) can't use a GPU; running on CPU. "
                    "Install the CUDA build: see cv_engine/README.md", requested, torch.__version__)
        return "cpu"
    if requested == "mps" and not (getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()):
        log.warning("DEVICE=mps but Apple GPU isn't available; running on CPU")
        return "cpu"
    return requested


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
        self.vision = VisionMonitor()
        self._recovered_until: dict[int, float] = {}

    def process(self, frame: np.ndarray, now: float, force_fall: bool = False) -> tuple[np.ndarray, list[FallEvent]]:
        """`now` is the frame's time: wall clock for a webcam, video time for a clip."""
        started = time.perf_counter()
        was_impaired = self.vision.status.impaired
        vision = self.vision.update(frame, now)
        if vision.impaired != was_impaired:
            if vision.impaired:
                log.warning("%s on %s: falls may be missed", vision.label, self.cfg.CAMERA_ID)
            else:
                log.info("vision restored on %s", self.cfg.CAMERA_ID)
        self.people = self.estimator(frame)
        events = self.detector.update(self.people, now)
        if force_fall and (target := largest_person(self.people)):
            if manual := self.detector.force_event(target, now):
                events.append(manual)

        if self._last_frame_at is not None and now > self._last_frame_at:
            instant = 1.0 / (now - self._last_frame_at)
            self.fps = instant if self.fps == 0 else FPS_SMOOTHING * self.fps + (1 - FPS_SMOOTHING) * instant
        self._last_frame_at = now

        for assessment in self.detector.pop_assessments():
            incident_id = event_id(self.cfg.CAMERA_ID, assessment.fall)
            log.warning("POST-FALL track=%s outcome=%s down=%.0fs motion=%.3f", assessment.fall.track_id,
                        assessment.outcome.value, assessment.seconds_down, assessment.motion)
            if assessment.outcome is Assessment.RECOVERED:
                self._recovered_until[assessment.fall.track_id] = now + RECOVERED_LABEL_S
            self.emitter.send_assessment(incident_id, assessment_payload(assessment, self.cfg.CAMERA_ID, self.cfg.ZONE_ID))

        states = {p.track_id: self.detector.state_of(p.track_id) for p in self.people}
        notes, unresponsive = self._post_fall_notes(now)
        status = f"{self.cfg.ZONE_ID} | {self.cfg.CAMERA_ID} | {self.fps:.0f} FPS | {len(self.people)} people"
        annotated = draw_frame(frame, self.people, states, status, skeleton_only=self.skeleton_only,
                               vision_warning=vision.label if vision.impaired else None, notes=notes,
                               alert_text=UNRESPONSIVE_ALERT if unresponsive else "FALL DETECTED")

        for event in events:
            # Same clock as `now`, plus the time this frame took to process.
            sent_at = now + (time.perf_counter() - started)
            if self.streamer:
                self.streamer.save_snapshot(event_id(self.cfg.CAMERA_ID, event), annotated)
            self.emitter.send(fall_payload(event, self.cfg.CAMERA_ID, self.cfg.ZONE_ID, sent_at, self.snapshot_base_url))
            log.warning("FALL track=%s conf=%.2f trigger=%s detection=%s", event.track_id, event.pose_confidence,
                        "manual" if event.manual else "auto", event.detection)

        if now - self._last_heartbeat_at >= self.cfg.HEARTBEAT_INTERVAL_S:
            self._last_heartbeat_at = now
            self.emitter.send(heartbeat_payload(self.cfg.CAMERA_ID, self.cfg.ZONE_ID, now, self.fps, len(self.people),
                                                vision=vision.reason or "ok"))

        if self.streamer:
            self.streamer.status = {"fps": round(self.fps, 1), "people_detected": len(self.people), "camera": "ok",
                                    "vision": vision.reason or "ok"}
            self.streamer.update_frame(annotated)
        return annotated, events

    def _post_fall_notes(self, now: float) -> tuple[dict[int, str], bool]:
        """Per-person labels like "DOWN 7s - NO MOVEMENT", and whether anyone is unresponsive."""
        notes, unresponsive = {}, False
        for person in self.people:
            down = self.detector.down_status(person.track_id, now)
            if down:
                seconds, outcome = down
                notes[person.track_id] = f"DOWN {seconds:.0f}s{OUTCOME_NOTES[outcome]}"
                unresponsive |= outcome is Assessment.UNRESPONSIVE
            elif (lying := self.detector.lying_seconds(person.track_id, now)) is not None:
                notes[person.track_id] = f"ON FLOOR {lying:.0f}s"
            elif self._recovered_until.get(person.track_id, 0) > now:
                notes[person.track_id] = "RECOVERED"
        return notes, unresponsive


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Call-Help CV engine")
    parser.add_argument("--video", help="replay a recorded clip instead of the webcam")
    parser.add_argument("--loop", action="store_true", help="restart the clip when it ends")
    parser.add_argument("--skeleton-only", action="store_true", help="privacy mode: never show or stream camera pixels")
    parser.add_argument("--no-window", action="store_true", help="don't open a preview window (headless)")
    parser.add_argument("--device", help="override DEVICE: cuda, mps or cpu")
    # Per-camera overrides, so several engines can share one cv_engine/.env.
    parser.add_argument("--camera-id", help="override CAMERA_ID, e.g. zone-1-cam-2")
    parser.add_argument("--zone-id", help='override ZONE_ID, e.g. "Forklift Corridor"')
    parser.add_argument("--camera-index", type=int, help="override CAMERA_INDEX (see --list-cameras)")
    parser.add_argument("--camera-url", help="network stream from a phone camera app, instead of --camera-index")
    parser.add_argument("--public-host", help="CV host address reachable by dashboard laptops; no credentials")
    parser.add_argument("--port", type=int, help="override STREAM_PORT; each camera needs its own")
    parser.add_argument("--list-cameras", action="store_true", help="show which camera indexes work, then exit")
    return parser.parse_args(argv)


def apply_overrides(cfg: EngineConfig, args: argparse.Namespace) -> EngineConfig:
    overrides = {
        "CAMERA_ID": args.camera_id,
        "ZONE_ID": args.zone_id,
        "CAMERA_INDEX": args.camera_index,
        "CAMERA_URL": args.camera_url,
        "STREAM_PORT": args.port,
        "PUBLIC_HOST": args.public_host,
        "DEVICE": args.device,
    }
    return dataclasses.replace(cfg, **{k: v for k, v in overrides.items() if v is not None})


def main(argv=None) -> None:
    # Heavy imports stay here so `Engine` can be imported and tested without torch.
    from cv_engine.detector.pose import PoseEstimator
    from cv_engine.transport.emitter import TelemetryEmitter
    from cv_engine.transport.streamer import MjpegStreamer

    args = parse_args(argv)
    if args.list_cameras:
        cameras = list_cameras()
        for index, width, height in cameras:
            print(f"camera index {index}: {width}x{height}")
        if not cameras:
            print("no cameras found")
        return

    cfg = apply_overrides(EngineConfig(), args)
    logging.basicConfig(level=logging.INFO, format=f"%(asctime)s {cfg.CAMERA_ID} %(levelname)s %(message)s")
    if cfg.CAMERA_AUTH not in {"basic", "digest"}:
        raise SystemExit("CAMERA_AUTH must be basic or digest")
    try:
        camera_headers = json.loads(cfg.CAMERA_HTTP_HEADERS)
        if not isinstance(camera_headers, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in camera_headers.items()):
            raise ValueError()
    except (ValueError, TypeError):
        raise SystemExit("CAMERA_HTTP_HEADERS must be a JSON object of header names and string values") from None
    device = usable_device(cfg.DEVICE)

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

    if args.video:
        capture = cv2.VideoCapture(args.video)
        if not capture.isOpened():
            raise SystemExit(f"could not open video {args.video}")
        video_fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
        camera = None
    else:
        capture = None
        source = f"HTTP/IP camera {cfg.CAMERA_ID}" if cfg.CAMERA_URL else f"camera index {cfg.CAMERA_INDEX}"
        opener = (lambda: open_stream(cfg.CAMERA_URL, username=cfg.CAMERA_USERNAME, password=cfg.CAMERA_PASSWORD, auth_type=cfg.CAMERA_AUTH, headers=camera_headers)) if cfg.CAMERA_URL else (lambda: open_camera(cfg.CAMERA_INDEX))
        camera = LiveCamera(opener, source)
        if not camera.open():
            log.warning("could not open %s yet; will keep retrying", source)
    clock_start, frame_index = time.time(), 0
    force_fall = False
    window_title = f"Call-Help {cfg.CAMERA_ID} ({cfg.ZONE_ID})"
    window_shown = False

    try:
        while True:
            if camera is None:
                ok, frame = capture.read()
                if not ok:
                    if args.loop:
                        capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        continue
                    break
                # Replays use the clip's own timeline so a slow laptop doesn't
                # stretch a fall and hide its drop_velocity.
                now = clock_start + frame_index / video_fps
                frame_index += 1
            else:
                frame = camera.read()
                if frame is None:
                    streamer.status = {**streamer.status, "camera": "reconnecting"}
                    if not args.no_window and window_shown and (
                            cv2.waitKey(50) & 0xFF in QUIT_KEYS or window_closed(window_title)):
                        break
                    time.sleep(0.05)
                    continue
                now = time.time()

            annotated, _ = engine.process(frame, now, force_fall=force_fall)
            force_fall = False

            if not args.no_window:
                cv2.imshow(window_title, annotated)
                key = cv2.waitKey(1) & 0xFF
                if not window_shown:
                    window_shown = True
                    log.info("to stop: click the video window and press q, or close it")
                elif key in QUIT_KEYS or window_closed(window_title):
                    break
                force_fall = key in (ord("f"), ord("F"))
    except KeyboardInterrupt:
        pass
    finally:
        if capture is not None:
            capture.release()
        if camera is not None:
            camera.release()
        cv2.destroyAllWindows()
        emitter.close()
        streamer.stop()
        log.info("stopped; %d telemetry messages delivered, %d falls undelivered, %d falls rejected by backend",
                 emitter.delivered, emitter.pending_falls, emitter.rejected)


if __name__ == "__main__":
    main()
