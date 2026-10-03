# Dev 2 sequential verification

FastAPI replaces Express by team decision. Each stage must pass before work advances
to the next stage. Existing code and mocked tests are not proof of live integration.
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

## Hours 3–10 — IN PROGRESS

Existing implementation: REST ingestion, deduplication, persistent incident log, Twilio adapter,
recipient allowlist, and labeled dry-run results. Local/mocked tests passed in the initial milestone.

Required verification after the first gate: real Supabase readback after REST ingestion; live Twilio
submission to the team's configured demo recipients; phone receipt confirmed by the user; duplicate
replay sends no second alert; failure paths preserve the incident and honest SMS status.
Seed tooling is available for Dev 4's historical data.

## Hours 10–16 — NOT ADVANCED

Existing implementation: camera WebSocket endpoint, dashboard broadcast endpoint, REST resync contract,
and backend Gemini context retrieval. These have local/mocked tests only.

Required verification: real CV sender connects, an event reaches the team's dashboard and database,
and the Coach uses the new incident. Dev 1 owns the camera pipeline; Dev 3 owns dashboard/chat UI.
The current checked-out frontend still uses sample data; full team integration is not complete.

## Hours 16–22 — NOT ADVANCED

Required verification: demo dry run, measured backend-to-dashboard event latency, reconnect/resync,
provider-outage behavior, confirmed phone receipt, and a documented fallback. Dev 4 owns rehearsal
coordination and recording the backup video. Fix defects before freezing the backend.

## Hours 22–24 — NOT ADVANCED

Dev 2 handoff: tested backend commit, setup instructions, environment checklist, API/system diagram
inputs, and known limitations. Dev 4 owns the Devpost submission and presentation. Do not represent
these external/team actions as done without evidence.
