import asyncio
import json
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException

from app.schemas import IncidentAlert


class TelemetryService:
    def __init__(self, settings, store, dispatcher, hub):
        self.settings, self.store, self.dispatcher, self.hub = settings, store, dispatcher, hub
        self.lock = asyncio.Lock()

    async def ingest(self, event):
        if event.event_type == "normal" or event.pose_confidence < self.settings.min_confidence:
            return {"status": "ignored", "reason": "normal_or_below_confidence_threshold"}
        identity = json.dumps(event.model_dump(mode="json", exclude={"event_id"}), sort_keys=True)
        incident_id = event.event_id or uuid5(NAMESPACE_URL, identity)
        async with self.lock:
            existing = await self.store.get(incident_id)
            if existing:
                if (existing.camera_id, existing.zone_id, existing.detected_at, existing.event_type,
                    existing.pose_confidence, existing.metadata) != (event.camera_id, event.zone_id,
                    event.timestamp, event.event_type, event.pose_confidence, event.metadata):
                    raise HTTPException(409, "event_id already belongs to different telemetry")
                return {"status": "duplicate", "incident": existing.model_dump(mode="json")}
            now = datetime.now(timezone.utc)
            recent = await self.store.list(camera_id=event.camera_id, zone_id=event.zone_id,
                event_type=event.event_type, limit=1, alert_history=True)
            suppress = any(0 <= (now - row.received_at).total_seconds() < self.settings.cooldown_seconds
                for row in recent)
            sms_status = "not_required"
            if event.event_type == "fall":
                sms_status = "cooldown" if suppress else "pending"
            incident = IncidentAlert(incident_id=incident_id, camera_id=event.camera_id,
                zone_id=event.zone_id, event_type=event.event_type, pose_confidence=event.pose_confidence,
                severity="medium" if event.event_type == "ppe_violation" else "high",
                description=f"Possible {event.event_type.replace('_', ' ')} detected",
                location=event.zone_id, detected_at=event.timestamp, received_at=now,
                sms_status=sms_status, metadata=event.metadata)
            if not await self.store.insert(incident):
                return {"status": "duplicate", "incident": (await self.store.get(incident_id)).model_dump(mode="json")}
        await self.hub.publish({"type": "incident.created", "incident": incident.model_dump(mode="json")})
        if incident.sms_status == "pending":
            status, results = await self.dispatcher.dispatch(incident)
            incident = await self.store.update(incident_id, {"sms_status": status, "sms_results": results})
            await self.hub.publish({"type": "incident.updated", "incident": incident.model_dump(mode="json")})
        return {"status": "received", "incident": incident.model_dump(mode="json")}
