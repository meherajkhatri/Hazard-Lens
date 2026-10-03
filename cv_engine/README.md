# Call-Help CV Engine (Dev 1)

Webcam → YOLOv8-pose → fall detection → backend telemetry + live MJPEG stream.
Full design and the code-terms glossary are in [`docs/dev1-cv-engine-plan.md`](../docs/dev1-cv-engine-plan.md).

## Setup (from the repo root)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r cv_engine/requirements.txt
python -m pytest -q cv_engine/tests      # camera-free tests
```

Download the weights **before** the venue (Ultralytics fetches `yolov8n-pose.pt`
into the working directory on first run). With the weights present, the
real-model tests run too instead of skipping.

## Run

```bash
DEVICE=cuda python -m cv_engine.run                          # Nvidia laptop
DEVICE=mps  python -m cv_engine.run                          # Apple Silicon
python -m cv_engine.run --video cv_engine/tests/clips/fall_03.mp4 --loop   # backup replay
python -m cv_engine.run --skeleton-only                      # privacy mode
```

Preview window keys: `q` quit, `f` manual fall for the largest person (sent with `trigger: "manual"`).

## Settings (environment variables)

| Variable | Default | Notes |
|---|---|---|
| `CAMERA_ID` | `zone-1-cam-1` | |
| `ZONE_ID` | `Zone 1` | |
| `CAMERA_INDEX` | `0` | try `1` if the laptop's built-in camera opens instead of the USB webcam |
| `BACKEND_URL` | `http://localhost:8000` | Dev 2's FastAPI server |
| `API_KEY` | empty | must equal the backend's `API_KEY` (required there for live Twilio SMS) |
| `STREAM_PORT` | `8001` | |
| `PUBLIC_HOST` | auto-detected LAN IP | set it if snapshot links point at the wrong interface |
| `MODEL_PATH` | `yolov8n-pose.pt` | |
| `DEVICE` | `cpu` | `cuda` / `mps` |

Fall thresholds live in `FallThresholds` in `config.py`.

## For Dev 2 (backend)

- Falls arrive at `POST /api/v1/telemetry` matching your `TelemetryEvent`, with a stable UUID
  `event_id` (resends come back `duplicate`) and `metadata.trigger` = `auto` or `manual`.
- Heartbeats are `event_type: "normal"` every 5s, which your backend ignores without storing.
- Every confirmed fall scores `pose_confidence` ≥ 0.736, so keep `MIN_CONFIDENCE` at 0.7 or lower.
- Set the same `API_KEY` on both sides; a mismatch shows up as `backend rejected ... (check API_KEY)` in the CV log.

## For Dev 3 (dashboard)

- Live feed: `<img src="http://<dev1-ip>:8001/stream">`
- Camera status: `GET http://<dev1-ip>:8001/health` → `{status, fps, people_detected, clients}`
- Fall snapshot: `metadata.snapshot_url` on each fall incident (also `/snapshot/<incident_id>.jpg`)
- Live incidents come from Dev 2's `/ws/incidents`, not from the CV engine
