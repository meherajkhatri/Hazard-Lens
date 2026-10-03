# Dev 2 sequential verification

FastAPI replaces Express by team decision. Each stage must pass before work advances
to the next stage, except for explicit user-approved deferrals recorded below.
Existing code and mocked tests are not proof of live integration.
Updated October 3, 2026.

## Hours 0–3 — PASSED

| Requirement | Evidence | Status |
| --- | --- | --- |
| Git repository and backend branch | `origin/backend`, first implementation commit `7bfbf6b` | Complete |
| Python/API environment | Project virtual environment, dependency check, test suite, and real Uvicorn HTTP startup test | Verified locally |
| JSON telemetry contract | `app/schemas.py`, examples and retry rules in `README.md` | Implemented and tested; team handoff still needed |
| Supabase incidents schema | `supabase/schema.sql` | Executed successfully in project `gygghvgwrcalviwjsspd` |
| Working Supabase persistence | `python -m app.verify_setup --write-probe` | Passed: columns, insert, readback, uniqueness, update |

Live project: `call-help-safety`, CALL_HELP organization, free plan, East US (North Virginia).
The user completed sign-in and project/password creation. The schema was installed through the SQL editor.
The existing server key and project URL are configured only in ignored `backend/.env`.
Live probe ID: `ff9094c4-11d5-4edf-8b14-a9d7a18ccfaa`.
SQL verification returned RLS enabled=true, anonymous SELECT=false, authenticated/browser SELECT=false,
and service-role INSERT=true. The real Uvicorn startup test also verifies local HTTP readiness and auth.

To close this gate:

1. Create or select the team's Supabase project.
2. Execute `supabase/schema.sql` in the project's SQL editor.
3. Set `STORAGE_BACKEND=supabase`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, and `API_KEY`
   in the ignored `backend/.env`; do not paste credentials into chat or commit them.
4. From `backend/`, run `.\.venv\Scripts\python.exe -m app.verify_setup --write-probe`.
5. Record the passed checks and returned probe ID here, then advance.

The probe retains one clearly labeled, simulated, resolved incident in `Setup Verification`.
It calls Supabase directly and never calls Twilio or the telemetry alert flow. Read-only verification
is available without `--write-probe`, but does not pass the gate because write access remains untested.
The command returns nonzero for missing configuration, incomplete checks, or failures; it never prints keys.

## Hours 3–10 — CORE VERIFIED; LIVE TWILIO DELAYED

Existing implementation: REST ingestion, deduplication, persistent incident log, Twilio adapter,
recipient allowlist, and labeled dry-run results. Local/mocked tests passed in the initial milestone.

Live API/database verification passed with `python -m app.verify_ingestion` on October 3, 2026.
Probe ID: `1ebd372c-cd58-49ac-b3ed-3c01eaf369af`. Verified readiness, ingestion, persisted dry-run status,
duplicate retries, conflicting-ID rejection, readback, acknowledgement, resolution, and readback after
recreating the FastAPI app. This used the in-process HTTP test harness against real Supabase; the
network listener is covered separately by the server startup test. All 27 automated tests pass.

Delayed dependency: Twilio console redirects to a login page that fails with `ERR_CONNECTION_RESET`
in the in-app browser (two attempts). On October 3 the user reported Twilio servers down and explicitly
authorized marking this delayed and advancing. A provider-wide outage was not independently verified.
No real SMS has been sent and phone delivery is not verified. Keep `SMS_MODE=dry_run`; do not label
dry-run results as sent. Resume live verification when the account, sender, and demo recipients are available.
Hours 10–16 may proceed under this exception; SMS delivery remains an open acceptance item.

Rehearsal handoff: local `MIN_CONFIDENCE=0.7`, `ALERT_COOLDOWN_SECONDS=0`; an identical copy of
the backend API key is prepared in ignored `backend/data/dev1.env` for private transfer to Dev 1.
The user will deliver the key privately to Dev 1. The public template keeps its default cooldown of 30 seconds.

Required verification after the first gate: real Supabase readback after REST ingestion; live Twilio
submission to the team's configured demo recipients; phone receipt confirmed by the user; duplicate
replay sends no second alert; failure paths preserve the incident and honest SMS status.
Seed tooling is available for Dev 4's historical data.

## Hours 10–16 — BACKEND MILESTONES COMPLETE

Existing implementation: camera WebSocket endpoint, dashboard broadcast endpoint, REST resync contract,
and backend Gemini context retrieval.

Backend transport milestone PASSED: `python -m app.verify_realtime` starts an actual Uvicorn
process and exercises real HTTP/WebSocket clients against Supabase. Probe ID:
`cb3d2784-b6f3-4a45-aa7f-dc68d4d83d79`. All 11 checks passed: storage readiness, wrong-key rejection,
invalid-payload rejection, camera-to-dashboard broadcast, acknowledgement/dry-run status,
SMS-status broadcast, duplicate retry handling, dashboard reconnect with REST resync, new-incident
Coach retrieval, probe resolution, and resolution broadcast. One observed event took 221.9 ms
from simulated camera send to dashboard receive; this is not a performance guarantee.
All 29 automated tests pass. SMS was forced to dry-run and Coach to local summary throughout.

This validates the backend interfaces with simulated clients, not the physical CV camera or Dev 3 UI.
Team-device end-to-end verification remains outstanding for this stage.

Dev 1 sender milestone PASSED: fast-forwarded the backend branch to merged main `527e650`
and ran `python -m app.verify_cv_integration` using the actual CV `TelemetryEmitter` and
`fall_payload` functions. Dev 1's sender uses REST with `X-API-Key`; the backend broadcasts to
dashboard WebSockets. No payload or authentication fixes were needed. Live Supabase probe:
`60802f3d-af91-5e01-8800-4fb4c0e0ff92`. All nine checks passed, including a confidence-0.7 fall,
duplicate retry, heartbeat, single persisted incident, preserved CV metadata/snapshot URL, and
resolution broadcast. Observed send-to-broadcast latency was 301.7 ms for this run.
The combined backend + Dev 1 emitter suite passes 41 tests. This used a synthetic FallEvent and
real transport code; physical camera detection, image serving, and cross-laptop networking still need rehearsal.

Required verification: real CV sender connects, an event reaches the team's dashboard and database,
and the Coach uses the new incident. Dev 1 owns the camera pipeline; Dev 3 owns dashboard/chat UI.
The user reports frontend completion; backend work proceeds to Gemini verification. This report is
not a claim that this agent has performed the physical cross-laptop rehearsal.

Coach acceptance preparation: added `python -m app.verify_coach`, which requires real credentials,
resolves a synthetic incident before model calls, checks a cited answer plus empty-zone retrieval,
and leaves SMS disabled. Gemini context preserves the simulated marker, and malformed, blocked, or
truncated provider responses fail explicitly. Transient provider failures (`429` and `5xx`) retry up
to three times with bounded backoff; targeted Coach/API suite: 28 tests passed.

Live Gemini acceptance PASSED with the user's `abhijohal09@gmail.com` AI Studio account and
`gemini-3.8-flash`. `python -m app.verify_coach` probe
`e54f0d51-9cd1-4ad9-8a0b-de3a241ca70c` persisted and resolved its simulated incident in Supabase,
then verified that Gemini cited that incident and returned no sources for an empty zone. SMS remained
in dry-run mode. The model had earlier returned a temporary `503 UNAVAILABLE`; bounded retries remain
in place for transient provider capacity failures. The full backend suite passes 39 tests.

## Hours 16–22 — NOT ADVANCED

Required verification: demo dry run, measured backend-to-dashboard event latency, reconnect/resync,
provider-outage behavior, confirmed phone receipt, and a documented fallback. Dev 4 owns rehearsal
coordination and recording the backup video. Fix defects before freezing the backend.

## Hours 22–24 — NOT ADVANCED

Dev 2 handoff: tested backend commit, setup instructions, environment checklist, API/system diagram
inputs, and known limitations. Dev 4 owns the Devpost submission and presentation. Do not represent
these external/team actions as done without evidence.
