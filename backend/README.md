# Hazard Lens backend

The FastAPI service accepts camera telemetry, stores incidents, broadcasts live
updates to the dashboard, sends optional Brevo email alerts, and provides the
optional Safety Coach. Video capture and inference run in `cv_engine`.

## Local development

From `backend/`:

```bash
../.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
../.venv/bin/python -m pytest -q
```

Use `STORAGE_BACKEND=sqlite` and `ALERT_PROVIDER=none` for offline development.
Set `API_KEY` before allowing network access. The frontend proxy and each CV
worker must use the same server-side key.

## Supabase

Run `supabase/schema.sql` for a new database. For an existing incidents table,
run `supabase/migrate_alerts.sql` once in the Supabase SQL editor, then set
`STORAGE_BACKEND=supabase`, `SUPABASE_URL`, and `SUPABASE_SECRET_KEY`.
The elevated Supabase key belongs only in the backend environment.

## Alerts

Set `ALERT_PROVIDER=brevo_email` and configure the Brevo SMTP login, SMTP key,
verified sender, and recipients. Automatic email is sent only when confidence
is strictly above `ALERT_MIN_CONFIDENCE` (default `0.9`). Use
`POST /api/v1/alerts/email` only for a configured-recipient test.
Verification scripts disable external alerts and do not prove live delivery.

## Verification

```bash
../.venv/bin/python -m app.verify_ingestion
../.venv/bin/python -m app.verify_realtime
../.venv/bin/python -m app.verify_cv_integration
```

These probes use labeled temporary incidents, check persistence, authentication,
deduplication, WebSocket broadcasts, and CV telemetry. They do not replace
physical camera, live email, or production deployment acceptance tests.

## Production notes

Use HTTPS/WSS through the reverse proxy configuration in `../deploy/`, keep
backend and CV ports private, rotate API/provider keys, and back up SQLite data
and incident snapshots with `../tools/backup_data.sh`.
