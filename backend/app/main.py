from fastapi import FastAPI

from app.schemas import IncidentAlert, SMSAlert, TelemetryEvent
from app.services.alert_dispatcher import AlertDispatcher

app = FastAPI(title="Call-Help Safety API", version="0.1.0")
alert_dispatcher = AlertDispatcher()
active_incidents: list[IncidentAlert] = []


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/telemetry")
async def ingest_telemetry(event: TelemetryEvent) -> dict[str, str]:
    if event.event_type.lower() in {"fall", "ppe_violation", "collision_risk"}:
        active_incidents.append(
            IncidentAlert(
                incident_id=f"{event.camera_id}-{int(event.timestamp.timestamp())}",
                severity="high",
                description=f"Detected {event.event_type}",
                location=event.camera_id,
                detected_at=event.timestamp,
            )
        )

    return {"status": "received"}


@app.get("/api/v1/incidents", response_model=list[IncidentAlert])
async def list_incidents() -> list[IncidentAlert]:
    return active_incidents


@app.post("/api/v1/alerts/sms")
async def send_sms_alert(alert: SMSAlert) -> dict[str, str]:
    return await alert_dispatcher.send_sms_alert(alert)
