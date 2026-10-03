"""LiveCamera reconnect logic with fake captures, plus a real network stream:
our own MjpegStreamer stands in for a phone camera app (same MJPEG format)."""

import threading
import time

import numpy as np

from cv_engine.camera import LiveCamera, open_stream
from cv_engine.transport.streamer import MjpegStreamer

FRAME = np.zeros((48, 64, 3), dtype=np.uint8)


class FakeCapture:
    def __init__(self, opened=True, frames_before_dropping=None):
        self.opened = opened
        self.remaining = frames_before_dropping
        self.released = False

    def isOpened(self):
        return self.opened

    def read(self):
        if self.remaining is not None:
            if self.remaining <= 0:
                return False, None
            self.remaining -= 1
        return True, FRAME

    def release(self):
        self.released = True


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_frames_flow_and_brief_hiccups_do_not_disconnect():
    captures = [FakeCapture(frames_before_dropping=3)]
    camera = LiveCamera(lambda: captures[-1], "phone", clock=Clock())
    assert camera.open()
    assert all(camera.read() is not None for _ in range(3))
    for _ in range(LiveCamera.MAX_FAILED_READS - 1):
        assert camera.read() is None
    assert camera.connected  # a few dropped frames are tolerated


def test_lost_camera_is_reopened_after_delay():
    clock = Clock()
    captures = [FakeCapture(frames_before_dropping=0)]
    camera = LiveCamera(lambda: captures[-1], "phone", clock=clock)
    camera.open()
    for _ in range(LiveCamera.MAX_FAILED_READS):
        camera.read()
    assert not camera.connected and captures[0].released

    captures.append(FakeCapture())
    assert camera.read() is None  # too soon to retry
    clock.t += LiveCamera.RECONNECT_DELAY_S
    assert camera.read() is None  # this call reopens
    assert camera.connected and camera.read() is not None


def test_camera_missing_at_start_keeps_retrying():
    clock = Clock()
    captures = [FakeCapture(opened=False)]
    camera = LiveCamera(lambda: captures[-1], "phone", clock=clock)
    assert not camera.open() and captures[0].released
    captures.append(FakeCapture())
    clock.t += LiveCamera.RECONNECT_DELAY_S
    camera.read()
    assert camera.connected


def _serve(streamer, stop, value):
    frame = np.full((240, 320, 3), value, dtype=np.uint8)
    while not stop.is_set():
        streamer.update_frame(frame)
        time.sleep(0.02)


def _read_until(camera, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        frame = camera.read()
        if frame is not None:
            return frame
        time.sleep(0.05)
    return None


def test_network_stream_survives_phone_disconnect_and_reconnect():
    phone = MjpegStreamer(host="127.0.0.1", port=0).start()
    port = phone.port
    stop = threading.Event()
    threading.Thread(target=_serve, args=(phone, stop, 200), daemon=True).start()
    camera = LiveCamera(lambda: open_stream(f"http://127.0.0.1:{port}/stream"), "phone")
    try:
        assert camera.open()
        frame = _read_until(camera)
        assert frame is not None and frame.shape == (240, 320, 3) and abs(int(frame.mean()) - 200) < 5

        # Phone app stops: the engine must keep running and report disconnected.
        stop.set()
        phone.stop()
        deadline = time.time() + 15
        while camera.connected and time.time() < deadline:
            camera.read()
        assert not camera.connected

        # Phone app comes back on the same address.
        phone = MjpegStreamer(host="127.0.0.1", port=port).start()
        stop = threading.Event()
        threading.Thread(target=_serve, args=(phone, stop, 90), daemon=True).start()
        frame = _read_until(camera, timeout=15)
        assert frame is not None and abs(int(frame.mean()) - 90) < 5
    finally:
        stop.set()
        camera.release()
        phone.stop()
