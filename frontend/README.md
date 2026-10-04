# Call-Help dashboard

The Next.js dashboard connects to the FastAPI backend for persistent incidents,
real-time updates, acknowledgment/resolution, automatic SMS status, and Safety
Coach questions. It no longer creates mock dispatches or invented incident data.

## Run locally

Start the backend first (see [backend setup](../backend/README.md)):

```sh
# From the repository root
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
cd backend
../.venv/bin/python -m app.seed
../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```sh
cd frontend
cp .env.example .env.local
npm ci
npm run dev
```

Open http://localhost:3000. Set `BACKEND_URL` to the backend's address and set
`API_KEY` to the same value as backend/.env. Both variables stay server-side.
Never put backend, Gemini, Supabase, or Twilio secrets in `NEXT_PUBLIC_*` variables.

This dashboard is for a trusted local/LAN demo: its server routes have no user
login, and anyone who can reach it can read/update incidents and query the Coach.
Add user authentication before exposing it on the public internet. The persistent
WebSocket bridge needs a long-running Node server (`npm start`), not static export.

## Camera and multi-laptop setup

Follow [the CV engine guide](../cv_engine/README.md) to run the detector. Set its
`BACKEND_URL` and `API_KEY` to the backend, and use `ZONE_ID=Zone 1`.
In frontend/.env.local, set:

```dotenv
NEXT_PUBLIC_CAMERA_STREAM_URL=http://CV-LAPTOP-IP:8001/stream
NEXT_PUBLIC_CAMERA_ZONE=Zone 1
# Optional: map every CV camera ID to its browser-reachable MJPEG stream.
NEXT_PUBLIC_CAMERA_STREAMS={"zone-1-cam-1":"http://CV-1-IP:8001/stream","zone-1-cam-2":"http://CV-2-IP:8001/stream"}
```

`NEXT_PUBLIC_CAMERA_STREAMS` is the multi-camera configuration. When an incident arrives, the
dashboard automatically selects the stream whose key matches the incident's `camera_id`; selecting
an incident also focuses its camera. Keep `NEXT_PUBLIC_CAMERA_STREAM_URL` for a single-camera fallback.
If no live mapping exists but the incident includes `metadata.snapshot_url`, the dashboard shows that
incident snapshot instead. Stream URLs must be reachable from the browser, not just the Next.js server.
Restart Next.js after changing configuration; `NEXT_PUBLIC_*` settings are fixed
at build time for production. HTTPS dashboards require HTTPS camera streams.
Bounding boxes come from the actual annotated MJPEG stream.

## Rehearsal

1. Keep backend `SMS_MODE=dry_run`. Run `python -m app.seed` from backend/ to add
   18 idempotent historical records without sending messages.
2. Click **Enable alert sound** to unlock audio in the browser.
3. Run `python -m app.simulate` from backend/ (with the backend URL/key options
   described in its guide), or use the CV engine's manual fall event. This creates
   a real stored incident and uses the backend's configured automatic SMS flow.
4. Check the live incident, zone, timeline, statistics, and actual SMS status.
5. Acknowledge it, reload, and confirm persistence. Open the timeline entry to
   close it. Other connected dashboards update automatically.
6. Ask the Coach about the selected zone. Without Gemini credentials, it clearly
   labels its response as a local count summary. With Gemini configured in the
   backend, it retrieves up to 50 recent incidents and returns source IDs.
7. Stop/restart the backend. The dashboard shows disconnection, retries its event
   stream, and refreshes persisted incidents on reconnection. It also reconciles
   via REST every 15 seconds. Existing records stay visible with a stale warning
   when retrieval fails.

SMS runs automatically on qualifying fall ingestion, subject to the backend
cooldown and deduplication. `dry_run` means no message was sent; `queued` does not
confirm delivery. There is no browser resend button that could send duplicates.
Configure real Twilio/Gemini/Supabase credentials only in backend/.env using the
backend guide. Live provider and physical-camera checks require those resources.

## Validation

```sh
npm run build
npm run lint
npm run test:integration
```

The integration test starts isolated backend/frontend processes with a temporary
SQLite database, test API key, dry-run SMS, and local Coach. It requires the root
`.venv` above and a completed frontend production build. It never contacts Twilio,
Gemini, or Supabase. Set `CALL_HELP_TEST_PYTHON` to use another Python environment.

## Data flow

CV → FastAPI telemetry → incident database + SMS → backend WebSocket → Next.js
server bridge → browser EventSource. REST reads/actions and Coach requests pass
through an allowlisted same-origin Next.js proxy. Reconnects fetch a fresh REST
snapshot; duplicate event IDs update existing rows. No backend secret is sent to
the browser.
