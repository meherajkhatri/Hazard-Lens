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
            # Cooldown is per zone, not per camera: two cameras on one zone see the
            # same fall, and that must be one text, not two.
            recent = await self.store.list(zone_id=event.zone_id,
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

    async def assess(self, incident_id, assessment):
        """Record the camera's post-fall outcome and escalate when needed.

        - unresponsive: urgent follow-up text, regardless of the cooldown
        - recovered: an "update" text, but only if an urgent one was sent
        - moving: recorded only
        Repeating the same outcome changes nothing and sends nothing.
        """
        async with self.lock:
            incident = await self.store.get(incident_id)
            if not incident:
                raise HTTPException(404, "Incident not found")
            if incident.event_type != "fall":
                raise HTTPException(409, "Only fall incidents take a post-fall assessment")
            previous = incident.metadata.get("assessment")
            if previous == assessment.outcome:
                return {"status": "duplicate", "incident": incident.model_dump(mode="json")}
            escalate = assessment.outcome == "unresponsive" or (
                assessment.outcome == "recovered" and previous == "unresponsive")
            labels = {"unresponsive": "NO MOVEMENT after the fall - possible medical emergency",
                      "moving": "still down but moving", "recovered": "got back up"}
            metadata = {**incident.metadata, "assessment": assessment.outcome,
                        "seconds_down": round(assessment.seconds_down, 1),
                        "assessed_at": assessment.observed_at.isoformat()}
            incident = await self.store.update(incident_id, {
                "metadata": metadata,
                "description": f"Possible fall detected; {labels[assessment.outcome]} "
                               f"({assessment.seconds_down:.0f}s down)"})
        await self.hub.publish({"type": "incident.updated", "incident": incident.model_dump(mode="json")})
        if escalate:
            status, results = await self.dispatcher.escalate(incident, assessment)
            incident = await self.store.update(incident_id, {
                "metadata": {**incident.metadata, f"{assessment.outcome}_sms": status},
                "sms_results": [*incident.sms_results, *results]})
            await self.hub.publish({"type": "incident.updated", "incident": incident.model_dump(mode="json")})
        return {"status": "received", "incident": incident.model_dump(mode="json")}
