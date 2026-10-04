from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import AliasChoices, AwareDatetime, BaseModel, ConfigDict, Field, field_validator


class TelemetryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)
    event_id: UUID | None = None
    camera_id: str = Field(min_length=1, max_length=100)
    zone_id: str = Field(min_length=1, max_length=100)
    timestamp: AwareDatetime
    event_type: Literal["fall", "ppe_violation", "collision_risk", "normal"] = Field(
        validation_alias=AliasChoices("event_type", "pose_event")
    )
    pose_confidence: float = Field(ge=0, le=1, validation_alias=AliasChoices("pose_confidence", "confidence_score"))
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict, max_length=20)

    @field_validator("timestamp")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)


class IncidentAlert(BaseModel):
    incident_id: UUID
    camera_id: str
    zone_id: str
    event_type: str
    pose_confidence: float
    severity: Literal["high", "medium"]
    description: str
    location: str
    detected_at: AwareDatetime
    received_at: AwareDatetime
    status: Literal["active", "acknowledged", "resolved"] = "active"
    sms_status: str = "not_required"
    sms_results: list[dict[str, str]] = Field(default_factory=list)
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class IncidentUpdate(BaseModel):
    status: Literal["acknowledged", "resolved"]


class SMSAlert(BaseModel):
    recipient: str = Field(pattern=r"^\+[1-9]\d{7,14}$")
    message: str = Field(min_length=1, max_length=1000)


class EmailAlert(BaseModel):
    recipient: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    subject: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=10_000)


class CoachRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=2000)
    zone_id: str | None = Field(default=None, min_length=1, max_length=100)
    since: AwareDatetime | None = None
    until: AwareDatetime | None = None


class FallAssessment(BaseModel):
    """What the camera saw after a fall (sent by the CV engine's post-fall check)."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    outcome: Literal["recovered", "unresponsive", "moving"]
    seconds_down: float = Field(ge=0, le=3600)
    motion: float = Field(ge=0, le=10)
    observed_at: AwareDatetime
    camera_id: str = Field(min_length=1, max_length=100)
    zone_id: str = Field(min_length=1, max_length=100)
