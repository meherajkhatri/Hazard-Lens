# Call-Help Safety

Call-Help is a starter industrial safety monitoring system that combines real-time computer vision telemetry with incident response workflows.

## Project Goals

<<<<<<< Updated upstream
- Receive and process video stream telemetry from edge cameras.
- Trigger SMS-style alert webhooks for urgent incidents.
- Provide a frontend dashboard for live incident monitoring.
- Offer an AI Safety Coach chat interface for operational guidance.

## Repository Structure

```
.
├── backend/
│   ├── app/
│   │   ├── cv/pose_tracker.py
│   │   ├── services/alert_dispatcher.py
│   │   ├── main.py
│   │   └── schemas.py
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── App.jsx
    │   ├── App.css
    │   └── main.jsx
    ├── index.html
    └── package.json
=======
```text
Camera → YOLOv8 pose detection → FastAPI → Next.js dashboard
                                  ├── SQLite or Supabase
                                  └── Optional email alerts
>>>>>>> Stashed changes
```

## Backend (FastAPI)

<<<<<<< Updated upstream
### Setup
=======
## Project structure

- `frontend/` — Next.js dashboard
- `backend/` — FastAPI incident API, storage, alerts, and Safety Coach
- `cv_engine/` — camera capture, YOLO pose tracking, fall detection, and stream
- `cv_api/` — optional browser-webcam detection API
- `cameras/` — camera configuration examples

## Requirements

- Python 3.10–3.12 (3.12 recommended)
- Node.js LTS and npm
- Git
- Webcam, USB camera, or reachable camera stream

Optional integrations include Supabase, Brevo, and Ollama.

## Quick start

Clone the repository and install dependencies:

```bash
git clone https://github.com/meherajkhatri/Hazard-Lens.git
cd Hazard-Lens

python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt -r cv_engine/requirements.txt

cp backend/.env.example backend/.env
cp cv_engine/.env.example cv_engine/.env
cp frontend/.env.example frontend/.env.local

cd frontend
npm ci
cd ..
```

Configure the copied environment files before starting the services:

- Use the same `API_KEY` in `backend/.env`, `cv_engine/.env`, and
  `frontend/.env.local`.
- For a local demo, set `STORAGE_BACKEND=sqlite` and
  `ALERT_PROVIDER=none` in `backend/.env`.
- Set `BACKEND_URL` and camera stream values in the camera and frontend files.
- Keep secrets in server-side `.env` files; never put them in `NEXT_PUBLIC_*`
  variables.

## Run the application

Run the backend, camera engine, and frontend in three separate terminals.
Complete the terminals in order.

### Terminal 1: Start the backend

1. Open a new terminal.
2. Go to the repository root and activate the virtual environment:

   ```bash
   cd /path/to/Hazard-Lens
   source .venv/bin/activate
   ```

3. Start the FastAPI backend:

   ```bash
   cd backend
   python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

4. Leave this terminal running. The backend is available at
   `http://127.0.0.1:8000`. Its health check is
   `http://127.0.0.1:8000/health`.

### Terminal 2: Start the CV engine

1. Open a second terminal.
2. Go to the repository root and activate the virtual environment:

   ```bash
   cd /path/to/Hazard-Lens
   source .venv/bin/activate
   ```

3. Run the local configuration check:

   ```bash
   python -m cv_engine.preflight --allow-local
   ```

4. If preflight reports `READY`, start the camera engine:

   ```bash
   python -m cv_engine.run
   ```

5. Allow camera access when prompted and leave this terminal running. The
   annotated stream is available at `http://127.0.0.1:8001/stream`.

### Terminal 3: Start the frontend

1. Open a third terminal.
2. Go to the frontend directory:

   ```bash
   cd /path/to/Hazard-Lens/frontend
   ```

3. Start the Next.js development server:

   ```bash
   npm run dev
   ```

4. Open `http://localhost:3000` in a browser.

Keep all three terminals running while using the application. Press
`Control + C` in each terminal to stop its service. Replace
`/path/to/Hazard-Lens` with the actual path to your clone.

## Optional Safety Coach

The Safety Coach uses Ollama. Start Ollama and download the model configured in
`backend/.env`:

```bash
ollama pull qwen2.5-coder:7b
ollama serve
```

## Useful commands

Seed sample incidents:
>>>>>>> Stashed changes

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

See [backend setup and integration guide](backend/README.md) for Windows setup, environment variables,
Supabase schema, WebSocket contracts, seed data, tests, and current operating limits.

### API

- `POST /api/v1/telemetry` – ingest validated camera events with duplicate detection.
- `GET /api/v1/incidents` – list/filter persisted incidents; PATCH by ID to acknowledge or resolve.
- `POST /api/v1/alerts/sms` – dry-run or Twilio dispatch to configured recipients.
- `POST /api/v1/coach/chat` – Gemini with retrieved incident context, or a labeled local summary.
- `/ws/telemetry` and `/ws/incidents` – live ingestion and dashboard events.

## Computer Vision Module

`backend/app/cv/pose_tracker.py` includes a stub `PoseTracker` class using OpenCV + Ultralytics model hooks for pose processing.

## Frontend (Next.js + React)

### Setup

```bash
cd frontend
npm install
npm run dev
```

### Integrated dashboard

The dashboard loads persisted incidents, subscribes to live backend events,
acknowledges/resolves incidents, displays actual automatic SMS status, embeds the
CV engine's annotated MJPEG stream, and submits zone-scoped Safety Coach queries.
See [frontend setup and rehearsal](frontend/README.md) for configuration, a
multi-laptop walkthrough, and automated integration checks.

### External setup remaining

<<<<<<< Updated upstream
Configure and verify Supabase, Twilio, and Gemini with your team's accounts, and
rehearse the camera on your actual hardware. SQLite, dry-run SMS, and the clearly
labeled local count summary work without external credentials.
=======
- Run the backend from `backend/` and the camera engine from the repository
  root so Python imports resolve correctly.
- Restart a service after changing its `.env` file.
- Do not expose this unauthenticated local/LAN prototype directly to the public
  internet.
- Existing SQLite records are migrated automatically from the old SMS fields
  when the backend opens the database. For an existing Supabase database, run
  `backend/supabase/migrate_alerts.sql` once in the Supabase SQL editor.
- For real email alerts, set `ALERT_PROVIDER=brevo_email` and follow the
  provider variables in `backend/.env.example`. Otherwise use
  `ALERT_PROVIDER=none`.

## License

See [LICENSE](LICENSE).
>>>>>>> Stashed changes
