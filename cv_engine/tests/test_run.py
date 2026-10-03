"""Engine tests with a scripted estimator, plus an end-to-end smoke test of
main() on a generated clip (needs ultralytics, fastapi and the weights)."""

import os
import threading
from pathlib import Path

import cv2
import numpy as np
import pytest
import requests

from cv_engine.config import EngineConfig
from cv_engine.detector.fall_state import FallDetector
from cv_engine.run import Engine, largest_person
from cv_engine.tests.synthetic import BODY_PX, make_pose

FPS = 30
FRAME = np.zeros((720, 640, 3), dtype=np.uint8)


class ListEmitter:
    def __init__(self):
        self.sent = []

    def send(self, payload):
        self.sent.append(payload)


class SnapshotRecorder:
    def __init__(self):
        self.snapshots, self.status, self.frames = {}, None, 0

    def save_snapshot(self, eid, img):
        self.snapshots[eid] = img

    def update_frame(self, img):
        self.frames += 1


def falling_person(t: float):
    """Stands for 1s, falls over 0.4s, then lies still."""
    k = min(max((t - 1.0) / 0.4, 0.0), 1.0)
    return [make_pose(1, hip_y=400 + 0.5 * BODY_PX * k, angle_deg=85 * k)]


def make_engine(script):
    clock = {"t": 0.0}
    emitter, streamer = ListEmitter(), SnapshotRecorder()
    engine = Engine(EngineConfig(), lambda frame: script(clock["t"]), FallDetector(), emitter, streamer,
                    snapshot_base_url="http://10.0.0.5:8001")
    return engine, emitter, streamer, clock


def play(engine, clock, seconds, start=0.0, force_at=None):
    for i in range(int(seconds * FPS)):
        clock["t"] = start + i / FPS
        engine.process(FRAME, clock["t"], force_fall=(force_at is not None and i == int(force_at * FPS)))


def test_engine_emits_one_fall_with_snapshot_and_heartbeats():
    engine, emitter, streamer, clock = make_engine(falling_person)
    play(engine, clock, seconds=11)

    falls = [p for p in emitter.sent if p["event_type"] == "fall"]
    beats = [p for p in emitter.sent if p["metadata"].get("heartbeat")]
    assert len(falls) == 1
    assert len(beats) == 3  # t = 0, 5, 10
    meta = falls[0]["metadata"]
    assert meta["trigger"] == "auto"
    assert meta["snapshot_url"].endswith(f"/snapshot/{falls[0]['event_id']}.jpg")
    assert falls[0]["event_id"] in streamer.snapshots
    assert falls[0]["pose_confidence"] >= 0.7
    assert 0 < meta["latency_ms"] < 2000
    assert streamer.frames == 11 * FPS
    assert engine.fps == pytest.approx(FPS, rel=0.01)


def test_force_fall_emits_manual_event_for_largest_person():
    engine, emitter, _, clock = make_engine(lambda t: [make_pose(1), make_pose(2, hip_x=100)])
    play(engine, clock, seconds=1, force_at=0.5)
    falls = [p for p in emitter.sent if p["event_type"] == "fall"]
    assert len(falls) == 1 and falls[0]["metadata"]["trigger"] == "manual"


def test_force_fall_with_nobody_in_frame_does_nothing():
    engine, emitter, _, clock = make_engine(lambda t: [])
    play(engine, clock, seconds=1, force_at=0.5)
    assert [p for p in emitter.sent if p["event_type"] == "fall"] == []


def test_largest_person_picks_biggest_box():
    from dataclasses import replace

    small = replace(make_pose(1), bbox=(0.0, 0.0, 100.0, 300.0))
    big = replace(make_pose(2), bbox=(0.0, 0.0, 200.0, 400.0))
    assert largest_person([small, big]).track_id == 2
    assert largest_person([]) is None


WEIGHTS = Path(os.getenv("MODEL_PATH", "yolov8n-pose.pt"))


@pytest.mark.skipif(not WEIGHTS.exists(), reason="yolov8n-pose.pt not available")
def test_main_end_to_end_on_generated_clip(tmp_path, monkeypatch, caplog):
    pytest.importorskip("ultralytics")
    from cv_engine.tests.test_emitter import _start_backend
    from cv_engine import run

    clip = tmp_path / "empty.avi"
    writer = cv2.VideoWriter(str(clip), cv2.VideoWriter_fourcc(*"MJPG"), 30, (320, 240))
    for i in range(45):
        writer.write(np.full((240, 320, 3), i * 5 % 255, dtype=np.uint8))
    writer.release()

    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server, thread = _start_backend(port, tmp_path)
    monkeypatch.setattr(run, "EngineConfig", lambda: EngineConfig(
        BACKEND_URL=f"http://127.0.0.1:{port}", STREAM_PORT=0, MODEL_PATH=str(WEIGHTS), PUBLIC_HOST="127.0.0.1"))
    try:
        run.main(["--video", str(clip), "--no-window", "--skeleton-only"])
        # Empty clip: heartbeats delivered, no incidents raised.
        assert requests.get(f"http://127.0.0.1:{port}/api/v1/incidents", timeout=2).json() == []
        assert "rejected" not in caplog.text.lower()
    finally:
        server.should_exit = True
        thread.join(5)
