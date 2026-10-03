# Dev 1 — CV Engine Plan (Call-Help, Hack Dearborn 5)

**Owner:** Dev 1 (CV/AI Engineer)
**Branch:** `lakshyabranch`
**Mission:** A person falls in front of the webcam → within ~1 second, the backend gets **one** clean `fall` event and the dashboard shows a red skeleton on a live feed. Nothing else matters until that works on stage.

---

## 1. Decisions locked up front

| Decision | Choice | Why |
|---|---|---|
| Pose model | **YOLOv8n-pose (Ultralytics)**, not MediaPipe | Already in `backend/requirements.txt`; does multi-person + bounding boxes + tracking IDs in one call. MediaPipe Pose tracks one person, so a judge walking into frame can steal the skeleton mid-demo. |
| Where the code lives | New top-level **`cv_engine/`** process, run on Dev 1's GPU laptop | It's an edge agent, not part of the API. Keeps torch/ultralytics out of Dev 2's backend install, and Dev 1 never blocks on backend merges. |
| Transport to backend | **HTTP `POST /api/v1/telemetry`** (already stubbed) | No WebSocket client needed on the CV side. Backend fans out to the dashboard via its own WS. Fewer moving parts. |
| Video to dashboard | **CV engine serves an MJPEG stream** (`http://<dev1-ip>:8001/stream`) with the skeleton drawn on it | Only one process can open the webcam. If the frontend tries to grab the camera too, one of them fails. Dashboard just uses `<img src=".../stream">`. |
| Fall logic | **Multi-signal + state machine + cooldown** (not just `w/h > 1.5`) | Aspect ratio alone fires when someone crouches, ties a shoe, or bends over, and fires every frame while they lie there, which spams SMS. |
| Payload | **Match the existing `TelemetryEvent` schema** in `backend/app/schemas.py` | The schema already exists. Don't invent a second contract (`zone_id` / `pose_event` / `confidence_score` from the plan doc get mapped into it; see §4). |

---

## 2. Folder layout

```
cv_engine/
├── requirements.txt        # ultralytics, opencv-python, requests, numpy, pytest
├── config.py               # EngineConfig (CAMERA_ID, ZONE_ID, BACKEND_URL, ...) + FallThresholds
├── run.py                  # entrypoint: capture → infer → detect → emit → stream
├── detector/
│   ├── types.py            # PersonPose, PoseFeatures, FallState, FallEvent (no heavy deps)
│   ├── pose.py             # PoseEstimator: YOLOv8-pose, model.track(persist=True) → list[PersonPose]
│   ├── features.py         # compute_features(): torso angle, bbox aspect, body scale, keypoint conf
│   └── fall_state.py       # FallDetector: per-track state machine + cooldown → list[FallEvent]
├── transport/
│   ├── emitter.py          # TelemetryEmitter: POST to backend, retry + local queue if backend is down
│   └── streamer.py         # MjpegStreamer on :8001 (/stream, /health, /snapshot/<event_id>.jpg)
├── overlay.py              # draws skeleton, box colored by FallState, status banner, FPS
└── tests/
    ├── clips/              # recorded test videos (gitignored)
    ├── test_features.py    # unit tests on synthetic keypoints, no camera needed
    └── test_fall_state.py  # unit tests on frame sequences, no camera needed
```

Run everything **from the repo root** as a module: `python -m cv_engine.run` (add `--video <path>` for replay). The package is named `transport/`, not `io/`, because a local `io` package would shadow Python's built-in `io` module and break numpy/OpenCV imports.

### Code terms (use these names everywhere: code, payloads, chat)

| Term | Meaning | Unit / values |
|---|---|---|
| `PersonPose` | One tracked person in one frame: `track_id`, `keypoints` (17×3: x, y, conf), `bbox` (x1, y1, x2, y2) | pixels |
| `PoseFeatures` | Per-frame features computed from a `PersonPose` | — |
| `torso_angle_deg` | Angle of hip-mid → shoulder-mid vs. vertical | 0° upright, 90° horizontal |
| `bbox_aspect` | bbox width / height | ratio |
| `body_scale` | Shoulder-mid → ankle-mid distance (orientation-independent "body height"); falls back to 3 × torso length if ankles aren't visible; capped at the bbox diagonal | pixels |
| `hip_y` | Hip-mid y coordinate (image y grows downward) | pixels |
| `keypoint_conf` | **Lowest** confidence among shoulders + hips (keypoints 5, 6, 11, 12). Minimum, not mean, so one bad joint can't hide behind three good ones | 0–1 |
| `drop_velocity` | How fast `hip_y` moves down, normalized by `body_scale` | body-heights / second |
| `FallState` | `UPRIGHT` (green box), `FALLING` (amber), `DOWN` (red) | enum |
| `FallDetector` | Holds one state machine per `track_id`; `update(people, now)` → `list[FallEvent]` | — |
| `FallEvent` | One confirmed fall; maps 1:1 to a `fall` telemetry payload | — |
| `pose_confidence` | Final score sent to the backend | 0–1 |
| `CAMERA_ID` / `ZONE_ID` | `"zone-1-cam-1"` / `"Zone 1"` | config |

`backend/app/cv/pose_tracker.py` stays as-is for now. Once `cv_engine/` works, we either delete it or make it a thin import. That's a call for Dev 2 later, not a blocker.

---

## 3. The fall-detection algorithm

Run per tracked person (ByteTrack ID from `model.track`). Use COCO keypoints: shoulders (5, 6), hips (11, 12), ankles (15, 16).

**Features per frame (`PoseFeatures`)**
1. **`torso_angle_deg`**: angle between (hip-mid → shoulder-mid) and vertical. Standing ≈ 0–20°, on the floor ≈ 70–90°.
2. **`bbox_aspect`**: `w / h`. Standing < 0.6, lying > 1.0.
3. **`drop_velocity`**: downward movement of `hip_y` over the last `FALL_DROP_WINDOW_S` (0.6s), divided by `body_scale` and by elapsed time. Normalizing by `body_scale` means it doesn't depend on distance from the camera.
4. **`keypoint_conf`**: lowest confidence among shoulders + hips. Frames below `MIN_KEYPOINT_CONF` (0.4) are skipped.

**State machine (`FallDetector`, one per `track_id`)**. Threshold names are the fields of `FallThresholds` in `config.py`:
```
UPRIGHT ──(drop_velocity ≥ FALL_DROP_VELOCITY = 0.5 /s,
           i.e. hips drop ≥ 30% of body height within 0.6s)──▶ FALLING
FALLING ──(horizontal for ≥ DOWN_CONFIRM_S = 1.0s)──▶ DOWN  → emit ONE FallEvent
           horizontal = torso_angle_deg ≥ DOWN_TORSO_MIN_DEG (60)
                        AND bbox_aspect ≥ DOWN_ASPECT_MIN (1.0)
FALLING ──(not horizontal FALLING_TIMEOUT_S = 1.5s after the drop)──▶ UPRIGHT   (crouch/sit, no event)
DOWN    ──(torso_angle_deg ≤ UPRIGHT_TORSO_MAX_DEG (30) for ≥ RECOVER_CONFIRM_S = 1.0s)──▶ UPRIGHT
cooldown: no second FallEvent for the same track_id within EVENT_COOLDOWN_S = 15s
tracks not seen for TRACK_TTL_S = 3s are forgotten
```
Why this works: a **slow** lie-down never enters `FALLING` (no fast hip drop). A **crouch** never satisfies the torso angle. A **real fall** satisfies both. If the tracker gives a person a new `track_id` while they're on the floor, the new track never sees a drop, so there's no duplicate alert. All thresholds live in `config.py` so they can be tuned live at the venue.

**`pose_confidence`** = (0.4 × min(`torso_angle_deg` / 90, 1) + 0.3 × min(`bbox_aspect` / 1.5, 1) + 0.3 × min(peak `drop_velocity` / 1.0, 1)) × `keypoint_conf`, clipped to [0, 1].

---

## 4. Telemetry contract (handshake with Dev 2, hour 0–1)

Conforms to the existing `TelemetryEvent` in `backend/app/schemas.py`:

```json
POST /api/v1/telemetry
{
  "camera_id": "zone-1-cam-1",
  "timestamp": "2026-10-03T21:14:07.412Z",
  "pose_confidence": 0.81,
  "event_type": "fall",
  "metadata": {
    "event_id": "zone-1-cam-1-3-1791062047412",
    "zone_id": "Zone 1",
    "track_id": 3,
    "torso_angle_deg": 82.4,
    "bbox_aspect": 1.47,
    "drop_velocity": 0.92,
    "keypoint_conf": 0.88,
    "snapshot_url": "http://<dev1-ip>:8001/snapshot/zone-1-cam-1-3-1791062047412.jpg",
    "latency_ms": 1252,
    "trigger": "auto"
  }
}
```

`event_id` = `<CAMERA_ID>-<track_id>-<epoch ms>`. `latency_ms` = time from the start of the drop to the moment the event is sent. `trigger` is `"auto"` for a detected fall and `"manual"` for the `F`-key backup, so the logs never pass a manual trigger off as a detection.

Mapping from the original plan: `zone_id` → `metadata.zone_id`, `pose_event` → `event_type`, `confidence_score` → `pose_confidence`.

Schema rules to respect: `pose_confidence` must be in [0, 1], and `metadata` values must be flat `str | int | float | bool` (no `null`, no nested objects or lists).

**Ask Dev 2 for:** (a) set incident `location` from `metadata.zone_id` (it currently uses `camera_id`); (b) dedupe server-side on `camera_id + track_id` within 15s as a second safety net against SMS spam.

**Heartbeat:** every 5s, `event_type: "heartbeat"` with `pose_confidence: 0.0`, `metadata.fps` and `metadata.people_detected`, so the dashboard can show "Camera online · 28 FPS". The backend already ignores non-incident event types, so this is safe.

---

## 5. Hour-by-hour (Dev 1 only)

| Hours | Goal | Done when |
|---|---|---|
| **0–1** | Check out the Logitech webcam from MLH (student ID). Mount it **high and angled down** (tripod or top of monitor, 1.5 m+ up, 3–4 m back). Agree on the §4 contract with Dev 2. | Full body is visible standing **and** lying on the floor. |
| **1–3** | `pose.py` + `overlay.py`: webcam → YOLOv8n-pose → skeleton drawn. Check GPU: `device="cuda"` (RTX) or `"mps"` (Apple Silicon). | ≥ 20 FPS with a skeleton on screen. |
| **3–4** | **Record test clips** (do this before writing detection logic): 5× walk, 5× sit in chair, 5× crouch/tie shoe, 5× slow lie-down, 10× fall (forward, backward, sideways). Put a mat down. | ~30 labeled clips in `tests/clips/`. |
| **4–7** | `types.py` + `features.py` + `fall_state.py` with unit tests. Add a `--video` flag so it runs on clips. Tune thresholds against the clips, not live. | All 10 falls trigger, **0** false alarms on the other 20. |
| **7–9** | `streamer.py`: MJPEG on `:8001/stream`, plus `/snapshot/<event_id>.jpg` and `/health`. Box colors by `FallState`: green = `UPRIGHT`, amber = `FALLING`, red = `DOWN`. | Dev 3 can embed the stream from another laptop on venue Wi-Fi. |
| **9–10** | `emitter.py`: POST with 2 retries, in-memory queue if the backend is down, heartbeat thread. | Fall shows up in `GET /api/v1/incidents`. |
| **10–14** | **Integration with Dev 2 + Dev 3.** Measure end-to-end latency (fall → dashboard red → phone SMS). | Full chain works 5/5 times, p95 < 2s to dashboard. |
| **14–16** | Hardening: re-tune under **venue lighting**, a second person walking through frame, partial occlusion, the camera bumped slightly. | Still 0 false alarms with 2 people in frame. |
| **16+** | **Code freeze.** Only threshold tweaks. Rehearse the fall 10+ times on the actual demo spot. Record the backup video. | Team has a 60s backup clip. |

---

## 6. Demo-day safeguards (what usually kills CV demos)

1. **Hotspot, not hall Wi-Fi.** Put Dev 1, 2, and 3's laptops on one phone hotspot. Better still, run the backend on Dev 1's laptop for the demo so the critical path is `localhost`.
2. **Hidden manual trigger.** Press `F` in the CV window to emit a real `fall` event for the most prominent person. This is a backup only, for when a stage-lighting problem stops detection. Practice so you never need it.
3. **`--video` replay mode.** If the webcam dies, run `python -m cv_engine.run --video cv_engine/tests/clips/fall_03.mp4` and the whole pipeline still works off a recorded clip.
4. **Warm start.** Load the model and run 10 dummy frames before going on stage. The first inference on a GPU can take 2–5s.
5. **Fall safely.** Kneel first, then roll onto your side. It still produces a fast hip drop and a horizontal torso. Bring a mat or jacket.
6. **Pin the camera.** Tape the tripod down. If someone bumps it, the thresholds can drift.
7. **Lock the frame.** Disable webcam auto-exposure and autofocus if the driver allows, to stop flicker under stage lights.

---

## 7. Stretch goals (only after hour 14, and only if §5 is green)

- **Privacy mode** (`--skeleton-only`): stream only the skeleton on a black background. Strong judge talking point for a workplace product: "we never store faces."
- **No-motion-after-fall escalation:** still `DOWN` after 10s → second event `event_type: "fall_unresponsive"`, severity critical.
- **Zone polygons:** split one camera view into "Loading Ramp" and "Forklift Corridor" by where the person's feet are.

Do **not** start PPE detection or forklift-collision detection. They're in the backend's event-type list, but each one is its own model and dataset. One flawless fall demo beats three flaky features.

---

## 8. Definition of done

- [ ] `python -m cv_engine.run` starts webcam inference at ≥ 20 FPS with a skeleton overlay
- [ ] 10/10 recorded falls detected, 0/20 false alarms on non-fall clips
- [ ] Exactly **one** `fall` event per fall (state machine + cooldown verified)
- [ ] Event appears in `GET /api/v1/incidents` in < 1s; dashboard turns red in < 2s
- [ ] MJPEG stream embedded in Dev 3's dashboard
- [ ] `--video` fallback and `F` manual trigger tested
- [ ] 60s backup demo video recorded
