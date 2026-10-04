# Hazard Lens

Hazard Lens is a workplace-safety monitoring prototype with camera-based fall
detection, a live incident dashboard, persistent storage, optional email alerts,
and an optional Ollama Safety Coach.

## Requirements

- Python 3.10–3.12
- Node.js LTS and npm
- A webcam, USB camera, or reachable camera stream

## Install

```bash
git clone https://github.com/meherajkhatri/Hazard-Lens.git
cd Hazard-Lens
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt -r cv_engine/requirements.txt
cp backend/.env.example backend/.env
cp cv_engine/.env.example cv_engine/.env
cp frontend/.env.example frontend/.env.local
cd frontend && npm ci && cd ..
```

For a local run, use `STORAGE_BACKEND=sqlite` and `ALERT_PROVIDER=none` in
`backend/.env`. Use the same `API_KEY` in the backend, CV engine, and frontend.

## Run in three terminals

Replace `/path/to/Hazard-Lens` with the repository path. Start the terminals in
this order and leave each one running.

### Terminal 1: Backend

```bash
cd /path/to/Hazard-Lens
source .venv/bin/activate
cd backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Check `http://127.0.0.1:8000/health`.

### Terminal 2: CV engine (camera 1)

```bash
cd /path/to/Hazard-Lens
source .venv/bin/activate
python -m cv_engine.preflight --allow-local
python -m cv_engine.run --camera-id zone-1-cam-1 --camera-index 0 --port 8001
```

Allow camera access when prompted. The stream is available at
`http://127.0.0.1:8001/stream`.

### Additional cameras

Run one CV process for each connected camera. Use a different camera index,
camera ID, and stream port for every process:

```bash
# Terminal 4: camera 2
cd /path/to/Hazard-Lens
source .venv/bin/activate
python -m cv_engine.run --camera-id zone-1-cam-2 --zone-id "Zone 1" --camera-index 1 --port 8002
```

List locally available camera indexes before starting the processes:

```bash
python -m cv_engine.run --list-cameras
```

For network cameras, replace `--camera-index N` with
`--camera-url http://camera-address/stream`. Each process recognizes people
and falls independently and sends incidents with its own `camera_id`.
To run several workers under one supervisor, create private files from
`cameras/camera-1.env.example` and `cameras/camera-2.env.example`, then run:

```bash
python tools/run_cameras.py --env-file cameras/camera-1.env --env-file cameras/camera-2.env
```

### Terminal 3: Frontend

```bash
cd /path/to/Hazard-Lens/frontend
npm run dev
```

Open `http://localhost:3000`. Stop services with `Control + C` in each terminal.

## Configuration

- `frontend/.env.local` should use `BACKEND_URL=http://127.0.0.1:8000` and map
  every annotated CV output in `NEXT_PUBLIC_CAMERA_STREAMS`, for example:

  ```dotenv
  NEXT_PUBLIC_CAMERA_STREAMS={"zone-1-cam-1":"http://127.0.0.1:8001/stream","zone-1-cam-2":"http://127.0.0.1:8002/stream"}
  NEXT_PUBLIC_CAMERA_ZONES={"zone-1-cam-1":"Zone 1","zone-1-cam-2":"Zone 1"}
  ```

  The dashboard's **Camera** selector can show one feed or all configured
  feeds at the same time. Use the CV output URLs, not raw camera URLs.
  `frontend/.env.local` takes precedence over `frontend/.env`; when the
  browser is on another device, use the CV host's LAN address instead of
  `127.0.0.1` for every camera stream.
- For Brevo email, set `ALERT_PROVIDER=brevo_email` and fill its variables in
  `backend/.env`.
- Automatic email alerts are sent only when model confidence is strictly above
  90%. Configure this with `ALERT_MIN_CONFIDENCE=0.9`. Incidents below that
  threshold are still stored in the dashboard but do not trigger email.
- Existing SQLite records are migrated automatically from the old SMS fields.
- For existing Supabase data, run `backend/supabase/migrate_alerts.sql` once.
- Keep credentials out of `NEXT_PUBLIC_*` variables and do not expose this
  unauthenticated prototype directly to the public internet.
- The API uses a shared server-side API key. Put Caddy or Nginx in front of the
  frontend for HTTPS; `deploy/Caddyfile.example` provides a starting point.
  Keep backend and CV ports private.
- Back up SQLite data and incident snapshots with `tools/backup_data.sh`.
  On macOS, copy `deploy/com.hazardlens.backup.plist.example`, replace
  `REPLACE_ME`, and load it with `launchctl bootstrap gui/$UID`.
- GitHub Actions runs backend, CV engine, and frontend checks on every push and
  pull request. Copy the Caddy template in `deploy/` for HTTPS deployment.

## CV accuracy measurement

Place labeled clips in one directory. Names beginning with `fall` are positive
examples; names such as `adl`, `sit`, or `nonfall` are negative examples:

```bash
cd cv_engine
../.venv/bin/python -m cv_engine.eval_clips /path/to/labeled-clips --sweep
```

The report includes falls caught, missed falls, false alarms, and the threshold
settings tested. Keep the labeled footage private; use `--export` to save only
pose skeletons for repeatable evaluation.

## Optional Safety Coach

```bash
ollama pull qwen2.5-coder:7b
ollama serve
```

## Checks

```bash
cd backend && ../.venv/bin/python -m pytest -q
cd ../cv_engine && ../.venv/bin/python -m pytest -q
cd ../frontend && npm run lint && npm run build
```

See [LICENSE](LICENSE).
