"""VisionMonitor: notices when a camera can no longer see properly.

Without this, glare, smoke or a covered lens make pose confidence drop, the
detector skips those frames, and the camera goes silent, which looks exactly
like "everything is fine". The monitor makes that state loud instead.

Checks, on a small grayscale copy of each frame:
- glare:  a large share of blown-out pixels (flashlight, sun, fire)
- dark:   very dark frame (covered lens, lights off)
- haze:   contrast collapses well below this camera's own normal (smoke, fog,
          a smeared lens). Relative to a learned baseline, so a plain wall
          doesn't count as smoke.
A state only changes after it has held for a moment, so one odd frame
doesn't flip the status.
"""

from dataclasses import dataclass

import cv2
import numpy as np

ANALYSIS_SIZE = (160, 120)
GLARE_PIXEL = 250
GLARE_FRACTION = 0.25
DARK_MEAN = 25.0
HAZE_CONTRAST_RATIO = 0.4  # impaired below 40% of the camera's normal contrast
BASELINE_SECONDS = 3.0  # healthy frames used to learn the normal contrast
BASELINE_ALPHA = 0.02  # how fast the baseline keeps adapting while healthy
IMPAIRED_AFTER_S = 1.0
CLEARED_AFTER_S = 2.0


@dataclass(frozen=True)
class FrameQuality:
    brightness: float  # mean gray level 0-255
    glare_fraction: float  # share of blown-out pixels
    contrast: float  # gray-level standard deviation


@dataclass(frozen=True)
class VisionStatus:
    impaired: bool
    reason: str | None  # "glare" | "dark" | "haze"
    quality: FrameQuality

    @property
    def label(self) -> str:
        return f"VISION IMPAIRED: {self.reason.upper()}" if self.impaired else "VISION OK"


def measure(frame: np.ndarray) -> FrameQuality:
    gray = cv2.cvtColor(cv2.resize(frame, ANALYSIS_SIZE, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
    return FrameQuality(
        brightness=float(gray.mean()),
        glare_fraction=float((gray >= GLARE_PIXEL).mean()),
        contrast=float(gray.std()),
    )


class VisionMonitor:
    def __init__(self) -> None:
        self.status = VisionStatus(False, None, FrameQuality(0.0, 0.0, 0.0))
        self._baseline_contrast: float | None = None
        self._baseline_frames: list[float] = []
        self._baseline_started: float | None = None
        self._candidate: str | None = None  # reason seen on the last frame, "" for ok
        self._candidate_since: float | None = None

    def _problem(self, q: FrameQuality) -> str | None:
        if q.glare_fraction >= GLARE_FRACTION:
            return "glare"
        if q.brightness <= DARK_MEAN:
            return "dark"
        if self._baseline_contrast and q.contrast < HAZE_CONTRAST_RATIO * self._baseline_contrast:
            return "haze"
        return None

    def _learn(self, q: FrameQuality, now: float) -> None:
        if self._baseline_contrast is None:
            if self._baseline_started is None:
                self._baseline_started = now
            self._baseline_frames.append(q.contrast)
            if now - self._baseline_started >= BASELINE_SECONDS:
                self._baseline_contrast = float(np.median(self._baseline_frames))
        else:
            self._baseline_contrast += BASELINE_ALPHA * (q.contrast - self._baseline_contrast)

    def update(self, frame: np.ndarray, now: float) -> VisionStatus:
        q = measure(frame)
        problem = self._problem(q)
        if problem is None and not self.status.impaired:
            self._learn(q, now)

        seen = problem or ""
        if seen != self._candidate:
            self._candidate, self._candidate_since = seen, now
        held = now - self._candidate_since

        if problem and held >= IMPAIRED_AFTER_S:
            self.status = VisionStatus(True, problem, q)
        elif not problem and self.status.impaired and held >= CLEARED_AFTER_S:
            self.status = VisionStatus(False, None, q)
        else:
            self.status = VisionStatus(self.status.impaired, self.status.reason, q)
        return self.status
