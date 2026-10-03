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
├── requirements.txt        # ultralytics, opencv-python, requests, numpy
├── config.py               # camera index, CAMERA_ID, ZONE_ID, BACKEND_URL, thresholds
├── run.py                  # entrypoint: capture → infer → detect → emit → stream
├── detector/
│   ├── pose.py             # YOLOv8-pose wrapper, model.track(persist=True) → per-person keypoints
│   ├── features.py         # torso angle, bbox aspect, hip-drop velocity, keypoint confidence
│   └── fall_state.py       # per-track state machine + cooldown
├── io/
│   ├── emitter.py          # POST to backend, retry + local queue if backend is down
│   └── streamer.py         # MJPEG server on :8001 (/stream, /health, /snapshot)
├── overlay.py              # draws skeleton, box (green → amber → red), status banner, FPS
└── tests/
    ├── clips/              # recorded test videos (gitignored if large)
    └── test_fall_state.py  # unit tests on feature sequences, no camera needed
```

`backend/app/cv/pose_tracker.py` stays as-is for now. Once `cv_engine/` works, we either delete it or make it a thin import. That's a call for Dev 2 later, not a blocker.

---

## 3. The fall-detection algorithm

Run per tracked person (ByteTrack ID from `model.track`). Use COCO keypoints: shoulders (5, 6), hips (11, 12), ankles (15, 16).

**Features per frame**
1. **Torso angle**: angle between (hip-mid → shoulder-mid) and vertical. Standing ≈ 0–20°, on the floor ≈ 70–90°.
2. **Bbox aspect**: `w / h`. Standing < 0.6, lying > 1.2.
3. **Hip-drop velocity**: change in hip-mid `y` over the last ~0.5 s, **normalized by body height** so it doesn't depend on distance from the camera.
4. **Keypoint confidence**: mean confidence of the 6 core joints. Ignore frames below 0.4.

**State machine (per track ID)**
```
UPRIGHT ──(hip drops > 30% body height in ≤0.6s)──▶ FALLING
FALLING ──(torso > 60° AND aspect > 1.0 for ≥ 1.0s)──▶ DOWN  → emit ONE `fall` event
FALLING ──(back upright within 1.5s)──▶ UPRIGHT               (was a crouch/sit, no event)
DOWN    ──(torso < 30° for ≥ 1.0s)──▶ UPRIGHT                 (person recovered)
cooldown: no second event for the same track ID for 15s
```
Why this works: a **slow** lie-down never enters `FALLING` (no fast hip drop). A **crouch** never satisfies the torso angle. A **real fall** satisfies both. All thresholds go in `config.py` so they can be tuned live at the venue.

**Confidence score sent to the backend** = weighted mix of (torso angle normalized, aspect normalized, drop velocity normalized) × keypoint confidence, clipped to [0, 1].

---

## 4. Telemetry contract (handshake with Dev 2, hour 0–1)

Conforms to the existing `TelemetryEvent` in `backend/app/schemas.py`:

```json
POST /api/v1/telemetry
{
  "camera_id": "zone-1-cam-1",
  "timestamp": "2026-10-03T21:14:07.412Z",
  "pose_confidence": 0.91,
  "event_type": "fall",
  "metadata": {
    "zone_id": "Zone 1",
    "track_id": 3,
    "torso_angle_deg": 82.4,
    "bbox_aspect": 1.47,
    "drop_velocity": 0.58,
    "snapshot_url": "http://<dev1-ip>:8001/snapshot/1696367647412.jpg",
    "latency_ms": 640
  }
}
```

Mapping from the original plan: `zone_id` → `metadata.zone_id`, `pose_event` → `event_type`, `confidence_score` → `pose_confidence`.

**Ask Dev 2 for:** (a) set incident `location` from `metadata.zone_id` (it currently uses `camera_id`); (b) dedupe server-side on `camera_id + track_id` within 15s as a second safety net against SMS spam.

**Heartbeat:** every 5s, `event_type: "heartbeat"` with `metadata.fps` and `metadata.people_detected`, so the dashboard can show "Camera online · 28 FPS". The backend already ignores non-incident event types, so this is safe.

---

## 5. Hour-by-hour (Dev 1 only)

| Hours | Goal | Done when |
|---|---|---|
| **0–1** | Check out the Logitech webcam from MLH (student ID). Mount it **high and angled down** (tripod or top of monitor, 1.5 m+ up, 3–4 m back). Agree on the §4 contract with Dev 2. | Full body is visible standing **and** lying on the floor. |
| **1–3** | `pose.py` + `overlay.py`: webcam → YOLOv8n-pose → skeleton drawn. Check GPU: `device="cuda"` (RTX) or `"mps"` (Apple Silicon). | ≥ 20 FPS with a skeleton on screen. |
| **3–4** | **Record test clips** (do this before writing detection logic): 5× walk, 5× sit in chair, 5× crouch/tie shoe, 5× slow lie-down, 10× fall (forward, backward, sideways). Put a mat down. | ~30 labeled clips in `tests/clips/`. |
| **4–7** | `features.py` + `fall_state.py`. Add a `--video` flag so it runs on clips. Tune thresholds against the clips, not live. | All 10 falls trigger, **0** false alarms on the other 20. |
| **7–9** | `streamer.py`: MJPEG on `:8001/stream`, plus `/snapshot` and `/health`. Box colors: green = upright, amber = falling, red = down. | Dev 3 can embed the stream from another laptop on venue Wi-Fi. |
| **9–10** | `emitter.py`: POST with 2 retries, in-memory queue if the backend is down, heartbeat thread. | Fall shows up in `GET /api/v1/incidents`. |
| **10–14** | **Integration with Dev 2 + Dev 3.** Measure end-to-end latency (fall → dashboard red → phone SMS). | Full chain works 5/5 times, p95 < 2s to dashboard. |
| **14–16** | Hardening: re-tune under **venue lighting**, a second person walking through frame, partial occlusion, the camera bumped slightly. | Still 0 false alarms with 2 people in frame. |
| **16+** | **Code freeze.** Only threshold tweaks. Rehearse the fall 10+ times on the actual demo spot. Record the backup video. | Team has a 60s backup clip. |

---

## 6. Demo-day safeguards (what usually kills CV demos)

1. **Hotspot, not hall Wi-Fi.** Put Dev 1, 2, and 3's laptops on one phone hotspot. Better still, run the backend on Dev 1's laptop for the demo so the critical path is `localhost`.
2. **Hidden manual trigger.** Press `F` in the CV window to emit a real `fall` event for the most prominent person. This is a backup only, for when a stage-lighting problem stops detection. Practice so you never need it.
3. **`--video` replay mode.** If the webcam dies, run `python run.py --video tests/clips/fall_03.mp4` and the whole pipeline still works off a recorded clip.
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

- [ ] `python cv_engine/run.py` starts webcam inference at ≥ 20 FPS with a skeleton overlay
- [ ] 10/10 recorded falls detected, 0/20 false alarms on non-fall clips
- [ ] Exactly **one** `fall` event per fall (state machine + cooldown verified)
- [ ] Event appears in `GET /api/v1/incidents` in < 1s; dashboard turns red in < 2s
- [ ] MJPEG stream embedded in Dev 3's dashboard
- [ ] `--video` fallback and `F` manual trigger tested
- [ ] 60s backup demo video recorded
