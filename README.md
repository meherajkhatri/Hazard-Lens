# Hazard Lens

Hazard Lens is a workplace safety monitoring prototype that combines camera-based fall detection, a live incident dashboard, persistent incident storage, email/SMS integrations, and an AI Safety Coach.

The camera engine uses YOLOv8 pose estimation to track people and evaluate falls over multiple frames. The dashboard displays camera streams and incident updates, and lets users acknowledge and resolve incidents. Detection can produce false positives or miss events; this prototype does not replace supervision or automatically contact emergency services.

Repository: https://github.com/meherajkhatri/Hazard-Lens

## Project structure

| Folder | Purpose |
| --- | --- |
| `frontend/` | Next.js / React dashboard and server-side backend proxy |
| `backend/` | FastAPI incident API, SQLite/Supabase storage, alerts, and Safety Coach |
| `cv_engine/` | Python camera capture, YOLO pose tracking, fall detection, and MJPEG streaming |
| `cv_api/` | Optional Flask API for frames captured by the browser webcam |
| `cameras/` | Example configurations for multiple cameras |
| `tools/` | Camera utilities |

The primary setup in this guide uses `cv_engine`:

```text
Camera → CV engine → FastAPI → SQLite or Supabase
             │          │
             │          ├── Email/SMS provider, when enabled
             │          └── Live incident updates → Next.js dashboard
             └── Annotated MJPEG stream → Browser

Dashboard → FastAPI Safety Coach → Ollama
```

The API supports fall, PPE-violation, collision-risk, and normal telemetry. Supported event types do not mean every detector is implemented by the camera engine; the main engine focuses on falls.

## Requirements

- Git and VS Code.
- Python **3.12** recommended. The camera dependencies support Python 3.10–3.12; avoid Python 3.13+ for this setup.
- A current Node.js LTS release with npm, compatible with Next.js 16.
- A webcam, USB camera, or reachable phone-camera stream.
- Internet access for dependency installation and initial model downloads.
- Optional: Supabase for shared storage, Brevo for real email alerts, and Ollama for the Safety Coach.

The commands below use **macOS/Linux terminals**. Open VS Code's **Terminal → New Terminal**. Each running service needs its own terminal.

## 1. Download and install

```bash
git clone https://github.com/meherajkhatri/Hazard-Lens.git
cd Hazard-Lens
code .
```

If you already have the repository, open its folder in VS Code instead. If `code` is unavailable, use **File → Open Folder**.

From the repository root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt -r cv_engine/requirements.txt

cp -n backend/.env.example backend/.env
cp -n cv_engine/.env.example cv_engine/.env
cp -n frontend/.env.example frontend/.env.local

cd frontend
npm ci
cd ..
```

`cp -n` preserves existing configuration files. If `python3.12` is unavailable, install Python 3.12 first, or use `python3` after checking that `python3 --version` reports a supported version.

## 2. Choose a backend configuration

The repository's backend defaults require **Supabase and Brevo**. Copying the example without filling credentials will not start the server. Choose one of the following configurations.

Keep each configuration in its own file. URLs must be plain text, without Markdown link syntax or escape backslashes. Never commit real credentials. Replace any credentials previously shared in chat or committed to source control.

### Option A: Local demo without external accounts

Set these values in `backend/.env`:

```dotenv
STORAGE_BACKEND=sqlite
SQLITE_PATH=data/call_help.sqlite3
API_KEY=replace-with-your-shared-key
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
MIN_CONFIDENCE=0.7
ALERT_COOLDOWN_SECONDS=30
ALERT_PROVIDER=twilio
SMS_MODE=dry_run
SMS_CHANNEL=sms
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5-coder:7b
```

Choose your own key and use the same value in the camera and frontend files below. This configuration stores incidents locally and does not send real SMS or email. With the backend launched from `backend/`, the database is `backend/data/call_help.sqlite3`.

### Option B: Supabase storage and Brevo email

1. Open your Supabase project's SQL editor.
2. Run the contents of `backend/supabase/schema.sql` to create the required database structure.
3. Obtain your Supabase project URL and server secret key.
4. Configure a verified sender and SMTP credentials in Brevo.
5. Set the following values in `backend/.env`, replacing every placeholder:

```dotenv
STORAGE_BACKEND=supabase
SQLITE_PATH=data/call_help.sqlite3
API_KEY=replace-with-your-shared-key
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
MIN_CONFIDENCE=0.7
ALERT_COOLDOWN_SECONDS=30

SUPABASE_URL=https://YOUR-PROJECT.supabase.co
SUPABASE_SECRET_KEY=YOUR-SUPABASE-SERVER-SECRET

ALERT_PROVIDER=brevo_email
BREVO_SMTP_LOGIN=YOUR-BREVO-SMTP-LOGIN
BREVO_SMTP_KEY=YOUR-BREVO-SMTP-KEY
BREVO_FROM_EMAIL=verified-sender@example.com
BREVO_FROM_NAME=Hazard Lens
BREVO_RECIPIENTS=recipient@example.com

SMS_MODE=dry_run
SMS_CHANNEL=sms
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5-coder:7b
```

**This enables real email alerts. `SMS_MODE=dry_run` does not disable Brevo when `ALERT_PROVIDER=brevo_email`.** To use Supabase without sending alerts, set `ALERT_PROVIDER=twilio` and `SMS_MODE=dry_run`. Preflight then needs `--allow-local` because its default policy expects both Supabase and Brevo.

Use comma-separated addresses for multiple Brevo recipients. The SMTP login is not necessarily the verified sender email. Keep the Supabase secret and provider credentials in the backend only. Switching storage does not migrate existing SQLite records.

## 3. Configure the camera and dashboard

For all services on one computer, set `cv_engine/.env`:

```dotenv
API_KEY=replace-with-your-shared-key
BACKEND_URL=http://127.0.0.1:8000
CAMERA_ID=zone-1-cam-1
ZONE_ID=Zone 1
CAMERA_URL=
DEVICE=cpu
STREAM_PORT=8001
```

An empty `CAMERA_URL` uses the default webcam. `DEVICE=cpu` is a portable starting point; Apple Silicon users can try `DEVICE=mps`.

Set `frontend/.env.local`:

```dotenv
BACKEND_URL=http://127.0.0.1:8000
API_KEY=replace-with-your-shared-key
NEXT_PUBLIC_CAMERA_MODE=stream
NEXT_PUBLIC_CAMERA_STREAM_URL=http://127.0.0.1:8001/stream
NEXT_PUBLIC_CAMERA_ZONE=Zone 1
NEXT_PUBLIC_CAMERA_ID=zone-1-cam-1
```

Use the **same actual API key** in all three files. `NEXT_PUBLIC_CAMERA_MODE=stream` selects the CV engine's annotated stream instead of the browser-webcam workflow. Never put API keys or provider secrets in `NEXT_PUBLIC_*` variables.

## 4. Start the app in three terminals

Open each terminal at the repository root unless the command says otherwise. Keep all three running.

### Terminal 1: Backend

If you previously exported local-demo settings, clear them so `.env` takes effect:

```bash
unset STORAGE_BACKEND ALERT_PROVIDER SMS_MODE
source .venv/bin/activate
cd backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Wait for **Application startup complete**. The reloader's “Uvicorn running” message alone does not prove startup succeeded.

- Health: http://127.0.0.1:8000/health
- Interactive API documentation: http://127.0.0.1:8000/docs

Optional demo history: before starting the server, or from a separate activated terminal in `backend/`, run:

```bash
python -m app.seed
```

This adds 18 labeled simulated historical incidents to the configured database. It is idempotent and does not send alerts. It is not required for startup.

### Terminal 2: Camera engine

From the repository root:

```bash
source .venv/bin/activate
python -m cv_engine.preflight --allow-local
```

The command above is for the local demo or an intentionally non-Brevo setup. For Supabase plus Brevo, use the stricter check:

```bash
python -m cv_engine.preflight
```

Once preflight reports READY:

```bash
python -m cv_engine.run
```

Allow camera access when prompted. The first run may download model weights. Open http://127.0.0.1:8001/stream to check the annotated video.

Preflight checks connectivity, storage reads, and telemetry compatibility; it does not prove email delivery or successful database writes.

### Terminal 3: Frontend

From the repository root:

```bash
cd frontend
npm run dev
```

Open **http://localhost:3000**. Enable alert sound in the dashboard if desired. Restart Next.js after changing its environment file.

Press **Control + C** in each terminal to stop the app. The CV preview also supports `q` to quit.

## 5. Enable the Safety Coach with Ollama

The current backend implementation uses **Ollama**, even though some older component documentation mentions Gemini or a local-summary fallback. Ollama is optional for the dashboard and camera, but required for Coach responses.

Install Ollama, start its application/service, and download the configured model:

```bash
ollama pull qwen2.5-coder:7b
```

If Ollama is not already running, use another terminal:

```bash
ollama serve
```

Keep `OLLAMA_URL` and `OLLAMA_MODEL` in `backend/.env` aligned with the running service. The Coach retrieves up to 50 matching incidents for context and cites incident IDs. An unavailable Ollama server causes Coach requests to fail without preventing the other services from running.

## Running across multiple computers

Use the actual reachable address of each service's computer. For example, use `35.7.254.198` only if it is currently assigned to and reachable on the intended host.

On the backend computer, allow trusted-network connections:

```bash
cd backend
../.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- In `cv_engine/.env`, set `BACKEND_URL=http://BACKEND-IP:8000`.
- In `frontend/.env.local`, set `BACKEND_URL=http://BACKEND-IP:8000`.
- Set `NEXT_PUBLIC_CAMERA_STREAM_URL=http://CAMERA-IP:8001/stream` to the camera computer's address.
- Use the same backend API key in its clients.
- Allow the needed ports through the host firewall on your trusted network.
- If accessing the frontend from another computer, run `npm run dev -- --hostname 0.0.0.0` and open `http://FRONTEND-IP:3000`.
- Add the actual dashboard origin to backend `CORS_ORIGINS` where needed.

`127.0.0.1` always means the computer making the request. Camera stream URLs must be reachable from the browser, while the frontend's `BACKEND_URL` must be reachable from the Next.js server.

The application is a trusted local/LAN prototype with no dashboard user login. Do not expose it directly to the public internet. HTTPS pages also require HTTPS camera streams.

### Multiple cameras

Each camera needs its own ID and, when running on the same computer, a different stream port. Inspect available cameras:

```bash
python -m cv_engine.run --list-cameras
```

Example second camera:

```bash
python -m cv_engine.run --camera-id zone-1-cam-2 --zone-id "Zone 1" --camera-index 1 --port 8002
```

Map camera IDs to browser-reachable streams in `frontend/.env.local`:

```dotenv
NEXT_PUBLIC_CAMERA_STREAMS={"zone-1-cam-1":"http://127.0.0.1:8001/stream","zone-1-cam-2":"http://127.0.0.1:8002/stream"}
```

For a phone camera, set `CAMERA_URL` to the actual video stream supplied by its camera app, such as `http://PHONE-IP:8080/video`.

## Alternative: Browser webcam mode

Use this instead of the standalone camera engine when you want the browser to capture frames for the Flask detection API.

From the repository root:

```bash
source .venv/bin/activate
python -m pip install -r cv_api/requirements.txt
cp -n cv_api/.env.example cv_api/.env
python -m cv_api.app
```

Keep the backend and frontend running. Set these frontend values and restart Next.js:

```dotenv
NEXT_PUBLIC_CAMERA_MODE=browser
NEXT_PUBLIC_CV_API_URL=http://127.0.0.1:5000
```

Open the dashboard on localhost, choose Start Camera, and allow camera access. Avoid running both camera workflows against the same webcam simultaneously.

The Flask API defaults to `EMERGENCY_MODE=false` and `TEST_MODE=true`: detected falls are logged to `backend/data/cv_api_falls.jsonl` and are not forwarded to the incident backend. To intentionally forward detections, set `EMERGENCY_MODE=true` and configure `BACKEND_URL` and the matching `API_KEY` in `cv_api/.env`; the backend's configured alert provider can then send real notifications.

The browser-camera workflow requires a secure browser context (localhost or HTTPS). For remote use, also configure the Flask allowed origins and a browser-reachable API URL.

## Verify the setup

1. Confirm backend `/health` responds and reports your intended modes.
2. Confirm camera preflight reports READY.
3. Confirm the MJPEG stream opens and appears in the dashboard.
4. For an alert-free rehearsal, use backend `ALERT_PROVIDER=twilio` and `SMS_MODE=dry_run`, then restart the backend.
5. With a person visible in the CV preview, press `f` to send a manual test fall. This submits a real incident; with Brevo enabled it can send real email.
6. Confirm the incident appears, acknowledge or resolve it, and reload the dashboard to verify persistence.
7. Ask the Coach a question after starting Ollama.

Provider submission is not proof of delivery. Check provider records and the recipient inbox when intentionally testing live alerts.

## Troubleshooting

| Error or symptom | Fix |
| --- | --- |
| `../.venv/bin/python: no such file or directory` | Create `.venv` in the repository root with `python3.12 -m venv .venv`, then install dependencies. The `../.venv` path only works from a direct child folder such as `backend/`. |
| `No module named app` | Run the backend from `backend/`. |
| `No module named cv_engine` | Run the camera engine from the repository root. |
| `Configure SUPABASE_URL ...` | Fill valid Supabase values, or explicitly choose the SQLite configuration above. |
| `Brevo email requires ...` | Fill all Brevo settings including the shared API key, or select `ALERT_PROVIDER=twilio` with `SMS_MODE=dry_run`. |
| `.env` edits have no effect | Restart the service. Exported shell variables take precedence; clear old overrides with `unset STORAGE_BACKEND ALERT_PROVIDER SMS_MODE`. Check other exported variables if necessary. |
| API returns `401` | Make the frontend/camera API keys match the backend key, then restart affected services. |
| Preflight rejects local modes | For intentional SQLite or non-Brevo development, use `python -m cv_engine.preflight --allow-local`. |
| Camera does not open | Grant camera access, close other apps using it, list cameras, and try `--camera-index 1`. |
| Stream is missing in the dashboard | Set `NEXT_PUBLIC_CAMERA_MODE=stream`, check the stream URL directly, and restart Next.js. |
| Connection refused or timeout | Confirm the service is running, the IP is correct, and the port is reachable. Remote backend clients require `--host 0.0.0.0`. |
| Coach returns an Ollama error | Start Ollama, pull the configured model, and check `OLLAMA_URL`. |
| NumPy/PyTorch installation fails | Confirm Python 3.10–3.12 and use a fresh compatible virtual environment; preserve any existing environment until its replacement works. |
| `Address already in use` | Stop the old process in its terminal or choose another port and update the related URLs. On macOS, port 5000 can also be occupied by AirPlay Receiver. |

## Developer checks

From the repository root with the virtual environment active:

```bash
python -m pip install -r backend/requirements-dev.txt
cd backend
python -m pytest -q
cd ..
python -m pytest -q cv_engine/tests
cd frontend
npm run lint
npm run build
```

Some camera checks require downloaded model weights. Real camera performance, Supabase connectivity, and provider delivery require checks with those resources; passing unit tests alone does not establish them.

## Windows terminal note

In PowerShell, create the environment with `py -3.12 -m venv .venv`. Replace `source .venv/bin/activate` with `.\.venv\Scripts\Activate.ps1`, and use `.venv\Scripts\python.exe` instead of `.venv/bin/python`. From `backend/`, the root interpreter is `..\.venv\Scripts\python.exe`. Copy example files with `Copy-Item` only when the destination does not already exist. Remove an exported override using `Remove-Item Env:STORAGE_BACKEND -ErrorAction SilentlyContinue` (repeat for other variables).

## License

See [LICENSE](LICENSE) in the repository.
