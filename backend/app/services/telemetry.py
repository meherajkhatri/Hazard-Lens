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

    @staticmethod
    def _alert_identity(camera_id, metadata):
        """Cooldown identity for one person/event, not a whole zone.

        `alert_group_id` is optional cross-camera correlation supplied by the CV
        layer. Without it, a local CV `track_id` identifies one person on one
        camera. A camera-only fallback keeps legacy senders safe from repeat
        alerts while never suppressing another camera's independent fall.
        """
        group = metadata.get("alert_group_id")
        if group not in (None, ""):
            return f"group:{group}"
        track = metadata.get("track_id")
        return f"camera:{camera_id}:track:{track}" if track is not None else f"camera:{camera_id}"

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
            # Distinct people must not hide one another's alerts. A sender may
            # provide alert_group_id when two cameras have correlated the same
            # person; otherwise camera_id + track_id is the alert identity.
            alert_identity = self._alert_identity(event.camera_id, event.metadata)
            recent = await self.store.list(zone_id=event.zone_id,
                event_type=event.event_type, limit=100, alert_history=True)
            suppress = any(
                self._alert_identity(row.camera_id, row.metadata) == alert_identity and
                0 <= (now - row.received_at).total_seconds() < self.settings.cooldown_seconds
                for row in recent)
            alert_status = "cooldown" if suppress else "pending"
            incident = IncidentAlert(incident_id=incident_id, camera_id=event.camera_id,
                zone_id=event.zone_id, event_type=event.event_type, pose_confidence=event.pose_confidence,
                severity="medium" if event.event_type == "ppe_violation" else "high",
                description=f"Possible {event.event_type.replace('_', ' ')} detected",
                location=event.zone_id, detected_at=event.timestamp, received_at=now,
                alert_status=alert_status, metadata=event.metadata)
            if not await self.store.insert(incident):
                return {"status": "duplicate", "incident": (await self.store.get(incident_id)).model_dump(mode="json")}
        await self.hub.publish({"type": "incident.created", "incident": incident.model_dump(mode="json")})
        if incident.alert_status == "pending":
            status, results = await self.dispatcher.dispatch(incident)
            incident = await self.store.update(incident_id, {"alert_status": status, "alert_results": results})
            await self.hub.publish({"type": "incident.updated", "incident": incident.model_dump(mode="json")})
        return {"status": "received", "incident": incident.model_dump(mode="json")}

    async def assess(self, incident_id, assessment):
        """Record the camera's post-fall outcome and escalate when needed.

        - unresponsive: urgent follow-up alert, regardless of the cooldown
        - recovered: an update alert, but only if an urgent one was sent
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
                "metadata": {**incident.metadata, f"{assessment.outcome}_alert": status},
                "alert_results": [*incident.alert_results, *results]})
            await self.hub.publish({"type": "incident.updated", "incident": incident.model_dump(mode="json")})
        return {"status": "received", "incident": incident.model_dump(mode="json")}
