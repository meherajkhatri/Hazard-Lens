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

Configure and verify Supabase, Twilio, and Gemini with your team's accounts, and
rehearse the camera on your actual hardware. SQLite, dry-run SMS, and the clearly
labeled local count summary work without external credentials.
