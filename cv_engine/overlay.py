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


def draw_person(img: np.ndarray, person: PersonPose, state: FallState) -> None:
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


def draw_frame(
    frame: np.ndarray,
    people: list[PersonPose],
    states: dict[int, FallState],
    status: str,
    skeleton_only: bool = False,
    vision_warning: str | None = None,
) -> np.ndarray:
    """Return an annotated copy of `frame`.

    `states` maps track_id -> FallState (missing ids draw as UPRIGHT).
    `skeleton_only` draws on black so no faces are shown or streamed.
    `vision_warning` adds an amber bar at the bottom, e.g. "VISION IMPAIRED: GLARE".
    """
    img = np.zeros_like(frame) if skeleton_only else frame.copy()
    for person in people:
        draw_person(img, person, states.get(person.track_id, FallState.UPRIGHT))

    alert = any(s is FallState.DOWN for s in states.values())
    h, w = img.shape[:2]
    cv2.rectangle(img, (0, 0), (w, BANNER_PX), (0, 0, 180) if alert else (40, 40, 40), -1)
    text = f"FALL DETECTED  |  {status}" if alert else status
    cv2.putText(img, text, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
    if alert:
        cv2.rectangle(img, (0, 0), (w - 1, h - 1), STATE_COLORS[FallState.DOWN], 6)
    if vision_warning:
        cv2.rectangle(img, (0, h - BANNER_PX), (w, h), VISION_WARNING_COLOR, -1)
        cv2.putText(img, f"{vision_warning}  |  detection unreliable", (10, h - 11),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 2)
    return img
