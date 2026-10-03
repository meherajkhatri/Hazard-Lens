# Call-Help Safety

Call-Help is a starter industrial safety monitoring system that combines real-time computer vision telemetry with incident response workflows.

## Project Goals

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
```

## Backend (FastAPI)

### Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### API Stubs

- `POST /api/v1/telemetry` – ingest pose/event telemetry from camera pipelines.
- `GET /api/v1/incidents` – list active incidents for dashboards.
- `POST /api/v1/alerts/sms` – webhook-style SMS dispatch integration point.

## Computer Vision Module

`backend/app/cv/pose_tracker.py` includes a stub `PoseTracker` class using OpenCV + Ultralytics model hooks for pose processing.

## Frontend (React + Vite)

### Setup

```bash
cd frontend
npm install
npm run dev
```

### UI Stubs

- Active incident list panel.
- AI Safety Coach chat interface.

## Next Steps

- Connect telemetry endpoint to streaming ingestion infrastructure.
- Replace SMS dispatcher stub with provider integration (Twilio, etc.).
- Persist incidents in a database and add acknowledgement workflows.
- Connect Safety Coach UI to an LLM-backed assistant API.
