# Frontend / Backend Integration Status

## Connected on UtkarshBranch
- GET /health -> backend/system status
- GET /api/v1/incidents -> real incident history
- PATCH /api/v1/incidents/{incident_id} -> acknowledge and resolve
- POST /api/v1/telemetry -> demo fall goes through the real telemetry pipeline
- WS /ws/incidents -> real-time incident.created / incident.updated UI updates
- POST /api/v1/coach/chat -> real Safety Coach/local backend summary
- Dashboard statistics and zones are derived from backend incident records

## Intentionally not faked
- No real camera stream endpoint exists, so the UI labels the visual as a CV event visualization, not a live camera.
- Manual SMS dispatch is not exposed as an incident endpoint. Fall SMS dispatch is handled automatically by backend telemetry.

## Integration flag
When backend API_KEY is non-empty, REST requires X-API-Key and WebSocket requires the key as its first message. A browser should not receive this server secret. Live Gemini/Twilio configuration currently requires API_KEY, so production-safe browser authentication needs a backend auth/proxy design before those modes can be exposed securely.

## Frontend config
NEXT_PUBLIC_API_URL defaults to http://127.0.0.1:8000.
