"""Persistent logs for the AI Safety Coach and reports.

Two outputs per camera, in LOG_DIR (default cv_engine/logs, gitignored):

- <camera_id>.log: the human-readable console log, rotated at 5 MB x 5 files
- <camera_id>-YYYY-MM-DD.events.jsonl: one JSON object per line for every fall,
  post-fall outcome, vision change, camera connection change and session
  start/stop. One file per day, so reports can pick a date range.

No images or video are ever written; only the events and their measurements.
"""

import json
import logging
import threading
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

DEFAULT_LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUPS = 5


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def safe_name(camera_id: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in camera_id)


def add_file_logging(logger: logging.Logger, log_dir: Path, camera_id: str, fmt: str) -> RotatingFileHandler:
    """Also write the console log, from every thread of this engine (including the
    telemetry sender), to a rotating file. Each camera runs as its own process, so
    files don't mix. Remove the returned handler when the engine stops."""
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{safe_name(camera_id)}.log"
    handler = RotatingFileHandler(path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8")
    handler.setFormatter(logging.Formatter(fmt))
    logger.addHandler(handler)
    return handler


class EventLog:
    """Appends one JSON line per event to a per-camera, per-day file. Thread-safe."""

    def __init__(self, log_dir: Path, camera_id: str, zone_id: str) -> None:
        self.log_dir = Path(log_dir)
        self.camera_id = camera_id
        self.zone_id = zone_id
        self._lock = threading.Lock()
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, ts: float) -> Path:
        day = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        return self.log_dir / f"{safe_name(self.camera_id)}-{day}.events.jsonl"

    def write(self, event: str, ts: float, **fields) -> None:
        record = {"event": event, "time": iso(ts), "camera_id": self.camera_id, "zone_id": self.zone_id, **fields}
        line = json.dumps(record, separators=(",", ":"), default=str)
        with self._lock, self.path_for(ts).open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def read_events(log_dir: Path, since: str | None = None, until: str | None = None) -> list[dict]:
    """All events from every camera's daily files, oldest first. `since`/`until`
    are YYYY-MM-DD dates (inclusive). Damaged lines are skipped."""
    events = []
    for path in sorted(Path(log_dir).glob("*.events.jsonl")):
        day = path.name.rsplit("-", 3)[-3:]
        date = "-".join(day).split(".")[0]
        if (since and date < since) or (until and date > until):
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return sorted(events, key=lambda e: e.get("time", ""))
