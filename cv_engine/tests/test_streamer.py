"""MjpegStreamer tests over real HTTP on a free local port."""

import threading
import time

import cv2
import numpy as np
import pytest
import requests

from cv_engine.transport.streamer import BOUNDARY, MjpegStreamer


@pytest.fixture
def streamer():
    s = MjpegStreamer(host="127.0.0.1", port=0).start()
    yield s
    s.stop()


def _url(s, path):
    return f"http://127.0.0.1:{s.port}{path}"


def _frame(value: int) -> np.ndarray:
    return np.full((240, 320, 3), value, dtype=np.uint8)


def _publish_until(streamer, stop, value=200):
    while not stop.is_set():
        streamer.update_frame(_frame(value))
        time.sleep(0.01)


def test_health_reports_status(streamer):
    streamer.status = {"fps": 27.5, "people_detected": 2}
    body = requests.get(_url(streamer, "/health"), timeout=2).json()
    assert body == {"status": "ok", "fps": 27.5, "people_detected": 2, "clients": 0}


def test_stream_delivers_decodable_jpeg_frames(streamer):
    stop = threading.Event()
    threading.Thread(target=_publish_until, args=(streamer, stop), daemon=True).start()
    try:
        with requests.get(_url(streamer, "/stream"), stream=True, timeout=3) as r:
            assert r.headers["Content-Type"] == f"multipart/x-mixed-replace; boundary={BOUNDARY}"
            assert r.headers["Access-Control-Allow-Origin"] == "*"
            data = b""
            for chunk in r.iter_content(4096):
                data += chunk
                if data.count(f"--{BOUNDARY}".encode()) >= 3:
                    break
        jpeg = data[data.index(b"\xff\xd8"): data.index(b"\xff\xd9") + 2]
        img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        assert img.shape == (240, 320, 3)
        assert abs(int(img.mean()) - 200) < 5
    finally:
        stop.set()


def test_frames_are_not_encoded_without_viewers(streamer):
    streamer.update_frame(_frame(10))
    assert streamer._frame is None


def test_client_count_returns_to_zero_after_viewer_leaves(streamer):
    stop = threading.Event()
    threading.Thread(target=_publish_until, args=(streamer, stop), daemon=True).start()
    try:
        with requests.get(_url(streamer, "/stream"), stream=True, timeout=3) as r:
            next(r.iter_content(1024))
            assert streamer.clients == 1
        deadline = time.time() + 3
        while streamer.clients and time.time() < deadline:
            time.sleep(0.05)
        assert streamer.clients == 0
    finally:
        stop.set()


def test_snapshot_served_by_event_id_and_unknown_is_404(streamer):
    streamer.save_snapshot("zone-1-cam-1-3-1791062047412", _frame(50))
    ok = requests.get(_url(streamer, "/snapshot/zone-1-cam-1-3-1791062047412.jpg"), timeout=2)
    assert ok.status_code == 200 and ok.headers["Content-Type"] == "image/jpeg"
    assert requests.get(_url(streamer, "/snapshot/nope.jpg"), timeout=2).status_code == 404
    assert requests.get(_url(streamer, "/snapshot/../../etc/passwd.jpg"), timeout=2).status_code == 404


def test_oldest_snapshots_are_evicted(streamer):
    from cv_engine.transport.streamer import MAX_SNAPSHOTS

    for i in range(MAX_SNAPSHOTS + 5):
        streamer.save_snapshot(f"e{i}", _frame(i))
    assert "e0" not in streamer._snapshots and f"e{MAX_SNAPSHOTS + 4}" in streamer._snapshots
