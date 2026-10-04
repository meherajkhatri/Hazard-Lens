"""Opening live cameras: USB webcams (including phones used as webcams) and
network streams from phone camera apps, with automatic reconnect."""

import logging
import sys
import time
from collections.abc import Callable

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


def open_stream(url: str) -> cv2.VideoCapture:
    """A phone camera app's stream, e.g. http://192.168.1.23:8080/video."""
    capture = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    # Keep only the newest frame so a slow network doesn't build up delay.
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
