# CALL_HELP backend

FastAPI provides incident ingestion, persistence, live dashboard events, fall SMS alerts,
and a Gemini Safety Coach. Camera inference and video streaming belong to the CV module;
this API accepts event JSON, not video frames. The existing frontend still uses sample data.

See [Dev 2 checkpoints](DEV2_CHECKPOINTS.md) for the sequential verification gates and live setup probe.
After configuring Supabase, `python -m app.verify_ingestion` exercises the actual FastAPI routes
in-process against the live database, retains a labeled resolved test incident, and always forces SMS
dry-run. It checks ingestion, retry handling, acknowledgement/resolution, and persistence across app restart.
This verifies the API/database path, not delivery of a real SMS or the network listener.

`python -m app.verify_realtime` starts a temporary localhost Uvicorn server and connects real
camera/dashboard WebSocket clients. It verifies authentication, invalid messages, fall broadcast,
retry deduplication, reconnect + REST resync, Coach retrieval, and resolution updates using configured
storage. It retains a labeled resolved probe incident, reports one observed broadcast latency, and
always forces dry-run SMS and the local Coach summary. This is a backend integration probe, not
proof of the team's physical camera, frontend UI, live Gemini, or SMS delivery. It stops its server on exit.

## Run locally (Python 3.12)

From `backend/`, in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m app.seed
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --ws-max-size 65536
```

On macOS/Linux use `.venv/bin/python` in place of `.\.venv\Scripts\python.exe`.
The tested dependency snapshot is `requirements-lock.txt`; install it for exact versions.
Camera dependencies are separate in `requirements-cv.txt` and are not needed on the API server.

Open http://127.0.0.1:8000/docs for the interactive API. SQLite persists records in
`backend/data/call_help.sqlite3` when launched from this directory. `.env` and data are ignored by Git.
The seed command adds 18 labeled simulated incidents across Zone 1, Zone 2, and Forklift Corridor.
It is idempotent, never sends SMS, and does not update dates when run again.

In a second terminal, from `backend/`:

```powershell
.\.venv\Scripts\python.exe -m app.simulate
.\.venv\Scripts\python.exe -m pytest -q
```

The simulator refuses a server using live SMS unless given `--allow-live-sms`.

## Configuration and providers

- Local defaults: SQLite, SMS dry-run, and a deterministic Coach count summary.
- Set `API_KEY` before allowing network access. REST clients send `X-API-Key`.
  This is a shared key for a trusted hackathon team, not end-user accounts or role-based authorization.
  All API key holders can read/update incidents and invoke providers. Add identity, authorization,
  request limits, and audit logging before a public deployment. Use HTTPS/WSS beyond localhost.
- `CORS_ORIGINS` is a comma-separated list of exact dashboard origins.
- Supabase: run `supabase/schema.sql` in its SQL editor, then set `STORAGE_BACKEND=supabase`,
  `SUPABASE_URL`, and `SUPABASE_SECRET_KEY` to a server secret (`sb_secret_...`) or legacy service-role JWT.
  RLS is enabled with no browser policies; only the backend uses the elevated key.
  Switching storage does not migrate local SQLite records.
- Twilio: set `SMS_MODE=twilio`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`,
  `TWILIO_FROM_NUMBER`, and comma-separated `SMS_RECIPIENTS` in E.164 format.
  Live mode requires `API_KEY`. The manual SMS endpoint accepts only configured recipients.
  Trial-account recipient restrictions still apply; configure recipients in Twilio.
- Gemini: set `GEMINI_API_KEY`, `GEMINI_MODEL` to an available `generateContent` model,
  and `API_KEY`. The Coach retrieves at most 50 recent matching incidents and includes IDs in its response.
  This is structured database retrieval, not vector search. Use explicit `zone_id`, `since`, and `until`
  for reliable scoping. Times are timezone-aware; use explicit boundaries for “today”.
  Without a Gemini key the response says `mode: local_summary`; provider errors return 502.

Provider credentials stay in `.env` on the server. Do not put them in frontend environment variables.

## CV event contract

`POST /api/v1/telemetry` or send the same JSON to `/ws/telemetry`:

```json
{
  "event_id": "7eef8dce-69c1-4fd0-88a7-adb560b14934",
  "camera_id": "webcam-1",
  "zone_id": "Zone 1",
  "timestamp": "2026-10-03T19:00:00Z",
  "pose_event": "fall",
  "confidence_score": 0.96,
  "metadata": {"track_id": "person-1"}
}
```

`event_type` and `pose_confidence` are accepted aliases for the original scaffold contract.
`zone_id` is now required. Event types: `fall`, `ppe_violation`, `collision_risk`, `normal`.
Timestamps must include a timezone. Confidence must be between 0 and 1.
Normal events and confidence below `MIN_CONFIDENCE` (default 0.7) return `ignored` without storage.

Send **one event per detected episode**, not one per video frame. Reuse the same UUID and payload
on retries. Identical qualifying events return `duplicate`, with no second incident or SMS.
Reusing an ID with different telemetry returns 409. If no ID is supplied, a deterministic ID is derived
from the normalized payload; a changed timestamp represents a new event.

Each qualifying event is persisted and broadcast. Only falls trigger automatic SMS.
`ALERT_COOLDOWN_SECONDS` (default 30) suppresses additional SMS for the same camera, zone, and event
type; it does not suppress incident records or dashboard events. Set it to 0 if each distinct event
must alert, including separate people in the same camera view.

### Dev 1 handoff and rehearsal

Keep `MIN_CONFIDENCE=0.7` (or a deliberately agreed lower threshold). Events at exactly 0.7
are accepted; below-threshold events return `ignored`, whereas a wrong API key returns 401
over REST or closes the WebSocket with code 1008. A CV log saying `check API_KEY` means to
compare the CV `API_KEY` with the backend's `API_KEY`, not the Supabase server key.

The local rehearsal configuration uses `ALERT_COOLDOWN_SECONDS=0`. Restart the running backend
after changing `.env`. Each rehearsal fall must use a new `event_id`; retries must keep the
original ID and payload and will still be deduplicated. With the default 30-second cooldown,
two distinct falls in the same camera/zone less than 30 seconds apart are both logged but
only the first attempts SMS. Restore 30 after rehearsal if that is the team's desired alert policy.

The matching Dev 1 key is provided locally in ignored `backend/data/dev1.env`. Transfer it privately
to Dev 1 and copy `API_KEY` into the CV environment; never commit or send the full backend `.env`.
REST sends it as `X-API-Key`; WebSockets send `{"api_key":"..."}` immediately after connecting.
Dev 1 also needs the backend laptop's reachable address: `http://<backend-LAN-IP>:8000` for REST,
or `ws://<backend-LAN-IP>:8000/ws/telemetry` for WebSockets. `localhost` on Dev 1's laptop points
to Dev 1's machine. For the trusted rehearsal LAN, run Uvicorn with `--host 0.0.0.0` and allow
the app through the local firewall as needed. No network exposure is enabled automatically here.
SMS remains dry-run until Twilio is configured and enabled; disabling cooldown does not enable SMS.

SMS results are persisted as `dry_run`, `not_configured`, `cooldown`, `pending`, a provider status such
as `queued`, `failed`, `unknown`, or `partial`. A queued message is not proof of delivery. A timeout is
`unknown` because the provider may have accepted the message. No automatic retries or delivery callbacks
are implemented. The API response waits for SMS submission; the first WebSocket event is published earlier.

## REST routes

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Process health and configured modes; public, no credentials returned |
| GET | `/api/v1/ready` | Verify storage is reachable |
| POST | `/api/v1/telemetry` | Create a qualifying incident and dispatch fall alert |
| GET | `/api/v1/incidents` | Newest first; `zone_id`, `status`, `since`, `until`, `limit` (1–500), `offset` |
| GET | `/api/v1/incidents/{id}` | Retrieve one incident |
| PATCH | `/api/v1/incidents/{id}` | `{"status":"acknowledged"}` or `{"status":"resolved"}` |
| POST | `/api/v1/alerts/sms` | Manual alert to an allowlisted recipient; not idempotent |
| POST | `/api/v1/coach/chat` | `{"question":"Summarize risks", "zone_id":"Zone 1"}`; optional `since`, `until` |

Resolved incidents cannot be reopened. List results include all statuses unless filtered.

## WebSocket integration

Use `/ws/incidents` for dashboard notifications and `/ws/telemetry` for camera ingestion.
When `API_KEY` is configured, send `{"api_key":"..."}` as the first message within five seconds.
Keys are not sent in query strings. Wait for `{"type":"connected"}` before sending telemetry.
If the key is empty, the server sends `connected` immediately. Browser origins must be allowlisted.

Dashboard events are `{"type":"incident.created", "incident":{...}}` and
`{"type":"incident.updated", "incident":{...}}`. Upsert by `incident_id`; play the alert chime
only on `incident.created`. Video overlays and chimes remain frontend/CV responsibilities.
Camera acknowledgements use `type: telemetry.result` and `status: received|duplicate|ignored`.
Validation and storage failures use `type: error` with numeric `status` and a `detail` string.

There is no event replay. After `connected`, fetch incidents through REST, merge buffered events by ID,
and refresh on reconnect. Slow clients are disconnected with code 1013 and must resync.

## Current operating limits

Run **one Uvicorn worker / one server instance**: live broadcasts and the cooldown lock are process-local.
Incident IDs are unique in storage, but multi-instance alert cooldowns need database locking and a shared broker.
The SMS flow is not a durable task queue: a crash after incident insertion can leave `pending` status.
Inspect those records before any manual resend; this implementation does not guarantee delivery.
The system is a hackathon prototype and does not contact emergency services automatically.

Tests exercise SQLite persistence, validation, auth, WebSockets, cooldown/deduplication,
seed data, and mocked provider contracts. Real Supabase, Twilio, and Gemini checks require your configured accounts.

Official provider references: [Supabase Data API](https://supabase.com/docs/guides/api/quickstart),
[Twilio Messages](https://www.twilio.com/docs/messaging/api/message-resource),
[Gemini generateContent](https://ai.google.dev/api/generate-content).
