from datetime import datetime

from pydantic import BaseModel, Field


class TelemetryEvent(BaseModel):
    camera_id: str = Field(..., description="Unique camera identifier")
    timestamp: datetime
    pose_confidence: float = Field(..., ge=0.0, le=1.0)
    event_type: str = Field(..., description="Type of safety incident detected")
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class SMSAlert(BaseModel):
    recipient: str = Field(..., description="Recipient phone number")
    message: str = Field(..., min_length=1)


class IncidentAlert(BaseModel):
    incident_id: str
    severity: str
    description: str
    location: str
    detected_at: datetime
