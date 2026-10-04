"""Opening live cameras: USB webcams (including phones used as webcams) and
network streams from phone camera apps, with automatic reconnect."""

import logging
import sys
import time
from collections.abc import Callable
from urllib.parse import urlsplit, urlunsplit, unquote

import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

import cv2
import numpy as np

log = logging.getLogger("cv_engine")

# Lower resolution keeps several USB webcams within one laptop's USB bandwidth;
# the pose model resizes to 640 anyway.
CAMERA_WIDTH, CAMERA_HEIGHT = 640, 480
MAX_CAMERA_INDEX = 6


def open_camera(index: int) -> cv2.VideoCapture:
    # DirectShow opens faster on Windows and handles several USB webcams better.
    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
    capture = cv2.VideoCapture(index, backend)
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
    return capture


class MjpegCapture:
    """HTTP MJPEG input with private Basic/Digest credentials or API-key headers.

    Implements the small VideoCapture interface used by LiveCamera. No source
    URL, response body, authentication data, or raw exception is logged.
    """
    MAX_BUFFER = 4 * 1024 * 1024

    def __init__(self, url, *, username="", password="", auth_type="basic", headers=None):
        self._session = requests.Session()
        self._response = None
        self._chunks = iter(())
        self._buffer = bytearray()
        self._opened = False
        parsed = urlsplit(url)
        if parsed.username is not None:
            username = username or unquote(parsed.username)
            password = password or unquote(parsed.password or "")
            url = urlunsplit((parsed.scheme, parsed.netloc.rsplit("@", 1)[-1], parsed.path, parsed.query, ""))
        auth = (HTTPDigestAuth if auth_type == "digest" else HTTPBasicAuth)(username, password) if username else None
        try:
            self._response = self._session.get(url, auth=auth, headers=headers or {}, stream=True,
                timeout=(3, 5), allow_redirects=False)
            self._response.raise_for_status()
            content_type = self._response.headers.get("Content-Type", "").lower()
            if self._response.status_code != 200 or not any(value in content_type for value in
                ("multipart/x-mixed-replace", "image/jpeg", "application/octet-stream")):
                self.release()
                return
            self._chunks = self._response.iter_content(chunk_size=4096)
            self._opened = True
        except requests.RequestException:
            self.release()

    def isOpened(self):
        return self._opened

    def read(self):
        if not self._opened:
            return False, None
        try:
            while True:
                start = self._buffer.find(b"\xff\xd8")
                end = self._buffer.find(b"\xff\xd9", start + 2) if start >= 0 else -1
                if end >= 0:
                    data = bytes(self._buffer[start:end + 2])
                    del self._buffer[:end + 2]
                    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
                    return frame is not None, frame
                if start > 0:
                    del self._buffer[:start]
                if len(self._buffer) > self.MAX_BUFFER:
                    self.release()
                    return False, None
                self._buffer.extend(next(self._chunks))
        except (requests.RequestException, StopIteration):
            self.release()
            return False, None

    def release(self):
        self._opened = False
        if self._response is not None:
            self._response.close()
        self._session.close()


def open_stream(url: str, *, username="", password="", auth_type="basic", headers=None):
    """HTTP/MJPEG uses requests for authentication; RTSP retains OpenCV."""
    if urlsplit(url).scheme in {"http", "https"}:
        return MjpegCapture(url, username=username, password=password, auth_type=auth_type, headers=headers)
    capture = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return capture


def list_cameras() -> list[tuple[int, int, int]]:
    """(index, width, height) for every camera index that delivers a frame."""
    found = []
    for index in range(MAX_CAMERA_INDEX):
        capture = open_camera(index)
        ok, frame = capture.read() if capture.isOpened() else (False, None)
        if ok and frame is not None:
            found.append((index, frame.shape[1], frame.shape[0]))
        capture.release()
    return found


class LiveCamera:
    """Reads frames from a live source and reconnects instead of exiting.

    A phone over Wi-Fi drops frames and connections; one hiccup must not stop
    the engine mid-demo. After MAX_FAILED_READS bad reads in a row the source is
    reopened every RECONNECT_DELAY_S until it comes back.
    """

    MAX_FAILED_READS = 15
    RECONNECT_DELAY_S = 2.0

    def __init__(self, opener: Callable[[], cv2.VideoCapture], name: str,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._opener = opener
        self.name = name
        self._clock = clock
        self._capture: cv2.VideoCapture | None = None
        self._failed_reads = 0
        self._last_attempt = float("-inf")
        self.connected = False

    def open(self) -> bool:
        self._last_attempt = self._clock()
        capture = self._opener()
        if capture.isOpened():
            self._capture = capture
            self._failed_reads = 0
            if not self.connected:
                log.info("camera %s connected", self.name)
            self.connected = True
            return True
        capture.release()
        return False

    def read(self) -> np.ndarray | None:
        """The next frame, or None while the camera is unavailable."""
        if self._capture is None:
            if self._clock() - self._last_attempt >= self.RECONNECT_DELAY_S:
                self.open()
            return None
        ok, frame = self._capture.read()
        if ok and frame is not None:
            self._failed_reads = 0
            return frame
        self._failed_reads += 1
        if self._failed_reads >= self.MAX_FAILED_READS:
            log.warning("camera %s lost; reconnecting every %.0fs", self.name, self.RECONNECT_DELAY_S)
            self.release()
            self.connected = False
        return None

    def release(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None
