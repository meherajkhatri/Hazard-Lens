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
| `STREAM_PORT` | `8001` | |
| `PUBLIC_HOST` | auto-detected LAN IP | set it if snapshot links point at the wrong interface |
| `MODEL_PATH` | `yolov8n-pose.pt` | |
| `DEVICE` | `cpu` | `cuda` / `mps` |

Fall thresholds live in `FallThresholds` in `config.py`.

## For Dev 2 (backend)

- Telemetry arrives at `POST /api/v1/telemetry` in the existing `TelemetryEvent` shape.
  `event_type` is `fall` or `heartbeat` (every 5s).
- Use `metadata.zone_id` for the incident location, and dedupe on `metadata.event_id`
  (a fall is retried until the backend returns 2xx).
- `metadata.trigger` is `auto` or `manual`.

## For Dev 3 (dashboard)

- Live feed: `<img src="http://<dev1-ip>:8001/stream">`
- Camera status: `GET http://<dev1-ip>:8001/health` → `{status, fps, people_detected, clients}`
- Fall snapshot: `metadata.snapshot_url` on each fall event
