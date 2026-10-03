"""MjpegStreamer: serves the annotated feed to the dashboard over plain HTTP.

    GET /stream                     multipart MJPEG, embed with <img src=".../stream">
    GET /health                     {"status": "ok", "fps": ..., "people_detected": ..., "clients": ...}
    GET /snapshot/<event_id>.jpg    frame saved when that FallEvent fired

Each frame is JPEG-encoded once and shared by every viewer.
"""

import json
import threading
import time
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np

BOUNDARY = "callhelpframe"
JPEG_QUALITY = 80
STREAM_MAX_FPS = 15.0
MAX_SNAPSHOTS = 50


def encode_jpeg(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        raise ValueError("JPEG encoding failed")
    return buf.tobytes()


class MjpegStreamer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8001) -> None:
        self._frame: bytes | None = None
        self._frame_id = 0
        self._last_encoded_at = 0.0
        self._cond = threading.Condition()
        self._snapshots: OrderedDict[str, bytes] = OrderedDict()
        self._snap_lock = threading.Lock()
        self.status = {"fps": 0.0, "people_detected": 0}
        self.clients = 0
        self._clients_lock = threading.Lock()
        self._server = ThreadingHTTPServer((host, port), self._handler_class())
        self._server.daemon_threads = True
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, name="mjpeg-streamer", daemon=True)

    def start(self) -> "MjpegStreamer":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        with self._cond:
            self._cond.notify_all()

    def update_frame(self, img: np.ndarray) -> None:
        """Publish a frame. Skips encoding when nobody is watching or above STREAM_MAX_FPS."""
        now = time.monotonic()
        if self.clients == 0 or now - self._last_encoded_at < 1.0 / STREAM_MAX_FPS:
            return
        jpeg = encode_jpeg(img)
        self._last_encoded_at = now
        with self._cond:
            self._frame = jpeg
            self._frame_id += 1
            self._cond.notify_all()

    def save_snapshot(self, event_id: str, img: np.ndarray) -> None:
        jpeg = encode_jpeg(img)
        with self._snap_lock:
            self._snapshots[event_id] = jpeg
            while len(self._snapshots) > MAX_SNAPSHOTS:
                self._snapshots.popitem(last=False)

    def _next_frame(self, last_id: int, timeout: float = 2.0) -> tuple[int, bytes | None]:
        with self._cond:
            self._cond.wait_for(lambda: self._frame_id != last_id, timeout=timeout)
            return self._frame_id, self._frame

    def _handler_class(self):
        streamer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:  # keep the console readable
                pass

            def _send_bytes(self, status: int, content_type: str, body: bytes) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                path = self.path.split("?", 1)[0]
                if path == "/stream":
                    self._stream()
                elif path == "/health":
                    body = json.dumps({"status": "ok", **streamer.status, "clients": streamer.clients})
                    self._send_bytes(200, "application/json", body.encode())
                elif path.startswith("/snapshot/") and path.endswith(".jpg"):
                    with streamer._snap_lock:
                        jpeg = streamer._snapshots.get(path[len("/snapshot/"):-len(".jpg")])
                    if jpeg is None:
                        self._send_bytes(404, "text/plain", b"snapshot not found")
                    else:
                        self._send_bytes(200, "image/jpeg", jpeg)
                else:
                    self._send_bytes(404, "text/plain", b"not found")

            def _stream(self) -> None:
                self.send_response(200)
                self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={BOUNDARY}")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                with streamer._clients_lock:
                    streamer.clients += 1
                last_id = -1
                try:
                    while streamer._thread.is_alive():
                        last_id, jpeg = streamer._next_frame(last_id)
                        if jpeg is None:
                            continue
                        self.wfile.write(
                            f"--{BOUNDARY}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(jpeg)}\r\n\r\n".encode()
                        )
                        self.wfile.write(jpeg + b"\r\n")
                except (BrokenPipeError, ConnectionResetError):
                    pass  # viewer closed the tab
                finally:
                    with streamer._clients_lock:
                        streamer.clients -= 1

        return Handler
