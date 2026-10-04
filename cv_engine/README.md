# Hazard Lens CV Engine (Dev 1)

Webcam → YOLOv8-pose → fall detection → backend telemetry + live MJPEG stream.
Full design and the code-terms glossary are in [`docs/dev1-cv-engine-plan.md`](../docs/dev1-cv-engine-plan.md).

## Setup (from the repo root)

**Use Python 3.10–3.12.** Ultralytics 8.3.0 needs numpy < 2, which has no prebuilt wheels for
Python 3.13+; pip then tries to compile numpy and fails with "Unknown compiler(s)" on Windows.
On an Nvidia laptop, install the CUDA build of PyTorch before the requirements
(`pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128`), otherwise
pip installs the CPU-only build. Check with
`python -c "import torch; print(torch.__version__, torch.cuda.is_available())"`: the version should
end in `+cu128` and print `True`. If not, the engine warns and runs on CPU.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r cv_engine/requirements.txt
python -m pytest -q cv_engine/tests      # camera-free tests
cp cv_engine/.env.example cv_engine/.env  # then paste API_KEY from Dev 2's private handoff
```

`cv_engine/.env` is gitignored. Never commit it, and never paste the key into code or chat.

Download the weights **before** the venue (Ultralytics fetches `yolov8n-pose.pt`
into the working directory on first run). With the weights present, the
real-model tests run too instead of skipping.

## Before going live

The backend runs on Dev 2's laptop. In `cv_engine/.env` set `BACKEND_URL=http://<dev2-ip>:8000`, then:

```bash
python -m cv_engine.preflight     # prints READY, or exactly what to fix
```

Dev 2 must start the backend with `--host 0.0.0.0` (the README's `127.0.0.1` only accepts
connections from Dev 2's own laptop), and both laptops should share a phone hotspot.

## Run

```bash
DEVICE=cuda python -m cv_engine.run                          # Nvidia laptop
DEVICE=mps  python -m cv_engine.run                          # Apple Silicon
python -m cv_engine.run --video cv_engine/tests/clips/fall_03.mp4 --loop   # backup replay
python -m cv_engine.run --skeleton-only                      # privacy mode
```

### Several cameras

One process per camera. They share `cv_engine/.env` (API key, backend URL) and each gets its own
id, zone, camera index and stream port:

```bash
python -m cv_engine.run --list-cameras      # find the indexes; the built-in webcam is often 0
python -m cv_engine.run --camera-id zone-1-cam-1 --zone-id "Zone 1" --camera-index 1 --port 8001
python -m cv_engine.run --camera-id zone-1-cam-2 --zone-id "Zone 1" --camera-index 2 --port 8002
python -m cv_engine.run --camera-id corridor-cam-1 --zone-id "Forklift Corridor" --camera-index 1 --port 8001   # on a second laptop
```

**Phones as cameras.** Preferred: a USB webcam app (Iriun, DroidCam, Camo) so Windows sees the
phone as a normal camera; use `--camera-index`. Over Wi-Fi: a camera app that serves a stream
(e.g. Android "IP Webcam"), then `--camera-url http://<phone-ip>:8080/video`. Live cameras
reconnect on their own if the phone drops out; `/health` shows `"camera": "reconnecting"` meanwhile.

Webcams open at 640x480 so several fit in one laptop's USB bandwidth. Two cameras on one zone report the same fall twice; the backend's alert
cooldown must be per camera and tracked person.

Preview window keys: `q` quit, `f` manual fall for the largest person (sent with `trigger: "manual"`).

## Tuning thresholds on recorded clips (GPU cluster or laptop)

Name clips so the label is in the file name: `fall_01.mp4` must trigger, anything else
(`sit_01.mp4`, `adl-01-cam0`) must not. A clip can be a video or a folder of frames.

```bash
python -m cv_engine.eval_clips path/to/clips --device cuda           # pass/fail table
python -m cv_engine.eval_clips path/to/clips --device cuda --sweep   # + best FallThresholds
```

Share results without sharing videos: `--export cv_engine/tests/data/real_clips.json.gz` saves
only the skeletons (joint positions over time, no images or faces). Commit that file and anyone
can replay it with `--from-export ... --sweep`. The table also shows each clip's peak hip-drop
speed, max torso angle and min height, which explains why a clip was missed or fired.

Pose extraction (the GPU-heavy part) runs once per clip and is cached in `path/to/clips/.pose_cache`,
so re-scoring and the 108-combination sweep take seconds. Keep clips and the cache out of the repo.

## Settings (`cv_engine/.env` or environment variables)

| Variable | Default | Notes |
|---|---|---|
| `CAMERA_ID` | `zone-1-cam-1` | |
| `ZONE_ID` | `Zone 1` | |
| `CAMERA_INDEX` | `0` | try `1` if the laptop's built-in camera opens instead of the USB webcam |
| `BACKEND_URL` | `http://localhost:8000` | Dev 2's FastAPI server |
| `API_KEY` | empty | must equal the backend's `API_KEY` |
| `STREAM_PORT` | `8001` | |
| `PUBLIC_HOST` | auto-detected LAN IP | set it if snapshot links point at the wrong interface |
| `MODEL_PATH` | `yolov8n-pose.pt` | |
| `DEVICE` | `cpu` | `cuda` / `mps` |

Fall thresholds live in `FallThresholds` in `config.py`.

## For Dev 2 (backend)

- Falls arrive at `POST /api/v1/telemetry` matching your `TelemetryEvent`, with a stable UUID
  `event_id` (resends come back `duplicate`) and `metadata.trigger` = `auto` or `manual`.
- Post-fall outcomes arrive at `POST /api/v1/incidents/{event_id}/assessment`; `unresponsive`
  sends an urgent text regardless of the cooldown (see backend/README.md).
- Heartbeats are `event_type: "normal"` every 5s, which your backend ignores without storing.
- Every confirmed fall scores `pose_confidence` >= 0.736, so keep `MIN_CONFIDENCE` at 0.7 or lower.
- Set the same `API_KEY` on both sides; a mismatch shows up as `backend rejected ... (check API_KEY)` in the CV log.

## For Dev 3 (dashboard)

- Live feed: `<img src="http://<dev1-ip>:8001/stream">`
- Camera status: `GET http://<dev1-ip>:8001/health` → `{status, fps, people_detected, clients}`
- Fall snapshot: `metadata.snapshot_url` on each fall incident (also `/snapshot/<incident_id>.jpg`)
- Live incidents come from Dev 2's `/ws/incidents`, not from the CV engine
