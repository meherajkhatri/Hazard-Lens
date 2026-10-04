# Hazard Lens

Hazard Lens is a workplace-safety monitoring prototype. It uses camera-based
fall detection, a live incident dashboard, persistent incident storage, alerts,
and an optional AI Safety Coach.

The primary workflow is:

```text
Camera → YOLOv8 pose detection → FastAPI → Next.js dashboard
                                  ├── SQLite or Supabase
                                  └── Optional email/SMS alerts
```

The system is a prototype: detections can be missed or incorrect, and it does
not replace supervision or automatically contact emergency services.

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

Optional integrations include Supabase, Brevo, Twilio, and Ollama.

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
- For a local demo, set `STORAGE_BACKEND=sqlite`,
  `ALERT_PROVIDER=twilio`, and `SMS_MODE=dry_run` in `backend/.env`.
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

```bash
cd backend
python -m app.seed
```

List available cameras:

```bash
python -m cv_engine.run --list-cameras
```

Run checks:

```bash
python -m pytest -q backend
python -m pytest -q cv_engine/tests
cd frontend && npm run lint && npm run build
```

## Notes

- Run the backend from `backend/` and the camera engine from the repository
  root so Python imports resolve correctly.
- Restart a service after changing its `.env` file.
- Do not expose this unauthenticated local/LAN prototype directly to the public
  internet.
- For Supabase storage or real email/SMS alerts, follow the example variables
  in `backend/.env.example` and configure the provider credentials securely.

## License

See [LICENSE](LICENSE).
