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

### Terminal 2: CV engine

```bash
cd /path/to/Hazard-Lens
source .venv/bin/activate
python -m cv_engine.preflight --allow-local
python -m cv_engine.run
```

Allow camera access when prompted. The stream is available at
`http://127.0.0.1:8001/stream`.

### Terminal 3: Frontend

```bash
cd /path/to/Hazard-Lens/frontend
npm run dev
```

Open `http://localhost:3000`. Stop services with `Control + C` in each terminal.

## Configuration

- `frontend/.env.local` should use `BACKEND_URL=http://127.0.0.1:8000` and
  `NEXT_PUBLIC_CAMERA_STREAM_URL=http://127.0.0.1:8001/stream`.
- For Brevo email, set `ALERT_PROVIDER=brevo_email` and fill its variables in
  `backend/.env`.
- Existing SQLite records are migrated automatically from the old SMS fields.
- For existing Supabase data, run `backend/supabase/migrate_alerts.sql` once.
- Keep credentials out of `NEXT_PUBLIC_*` variables and do not expose this
  unauthenticated prototype directly to the public internet.

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
