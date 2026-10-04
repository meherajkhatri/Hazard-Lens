"""Draws skeletons, FallState-colored boxes and a status banner onto frames."""

import cv2
import numpy as np

from cv_engine.detector.types import FallState, PersonPose

# BGR colors per FallState: green, amber, red.
STATE_COLORS = {
    FallState.UPRIGHT: (0, 200, 0),
    FallState.FALLING: (0, 165, 255),
    FallState.DOWN: (0, 0, 255),
}

# COCO-17 skeleton edges.
SKELETON = [
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 11), (6, 12), (11, 12),
    (11, 13), (13, 15), (12, 14), (14, 16),
    (0, 1), (0, 2), (1, 3), (2, 4),
]
VISION_WARNING_COLOR = (0, 140, 255)  # BGR amber
MIN_DRAW_CONF = 0.3
BANNER_PX = 36


def put_fitted_text(img: np.ndarray, text: str, origin: tuple[int, int], color, scale: float = 0.65,
                    thickness: int = 2) -> None:
    """putText that shrinks the font so the text fits the frame width."""
    max_width = img.shape[1] - origin[0] - 8
    (width, _), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)
    if width > max_width:
        scale *= max_width / width
        thickness = 1 if scale < 0.5 else thickness
    cv2.putText(img, text, origin, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness)


def draw_person(img: np.ndarray, person: PersonPose, state: FallState, note: str | None = None) -> None:
    color = STATE_COLORS[state]
    kps = person.keypoints
    for a, b in SKELETON:
        if kps[a, 2] >= MIN_DRAW_CONF and kps[b, 2] >= MIN_DRAW_CONF:
            cv2.line(img, (int(kps[a, 0]), int(kps[a, 1])), (int(kps[b, 0]), int(kps[b, 1])), color, 2)
    for x, y, conf in kps:
        if conf >= MIN_DRAW_CONF:
            cv2.circle(img, (int(x), int(y)), 3, (255, 255, 255), -1)

    x1, y1, x2, y2 = (int(v) for v in person.bbox)
    cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
    label = f"ID {person.track_id} {state.value}"
    cv2.putText(img, label, (x1, max(y1 - 6, BANNER_PX + 14)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
    if note:
        # Under the box, or inside its bottom edge when the box reaches the bottom
        # of the frame (a fallen person often does). Dark backing keeps it readable.
        h = img.shape[0]
        y = y2 + 22 if y2 + 22 < h - BANNER_PX else y2 - 10
        x = max(x1, 0)
        (tw, th), _ = cv2.getTextSize(note, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(img, (x, y - th - 6), (min(x + tw + 8, img.shape[1] - 1), y + 6), (0, 0, 0), -1)
        put_fitted_text(img, note, (x + 4, y), color, scale=0.6)


def draw_frame(
    frame: np.ndarray,
    people: list[PersonPose],
    states: dict[int, FallState],
    status: str,
    skeleton_only: bool = False,
    vision_warning: str | None = None,
    notes: dict[int, str] | None = None,
    alert_text: str = "FALL DETECTED",
) -> np.ndarray:
    """Return an annotated copy of `frame`.

    `states` maps track_id -> FallState (missing ids draw as UPRIGHT).
    `skeleton_only` draws on black so no faces are shown or streamed.
    `vision_warning` adds an amber bar at the bottom, e.g. "VISION IMPAIRED: GLARE".
    `notes` maps track_id -> text drawn under that person, e.g. "DOWN 7s".
    `alert_text` is the banner text while someone is DOWN.
    """
    img = np.zeros_like(frame) if skeleton_only else frame.copy()
    for person in people:
        draw_person(img, person, states.get(person.track_id, FallState.UPRIGHT), (notes or {}).get(person.track_id))

    alert = any(s is FallState.DOWN for s in states.values())
    h, w = img.shape[:2]
    cv2.rectangle(img, (0, 0), (w, BANNER_PX), (0, 0, 180) if alert else (40, 40, 40), -1)
    text = f"{alert_text}  |  {status}" if alert else status
    put_fitted_text(img, text, (10, 25), (255, 255, 255))
    if alert:
        cv2.rectangle(img, (0, 0), (w - 1, h - 1), STATE_COLORS[FallState.DOWN], 6)
    if vision_warning:
        cv2.rectangle(img, (0, h - BANNER_PX), (w, h), VISION_WARNING_COLOR, -1)
        put_fitted_text(img, f"{vision_warning}  |  detection unreliable", (10, h - 11), (0, 0, 0))
    return img
