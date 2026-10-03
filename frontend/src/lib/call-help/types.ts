export type BackendIncident = {
  incident_id: string;
  camera_id: string;
  zone_id: string;
  event_type: string;
  pose_confidence: number;
  severity: "high" | "medium";
  description: string;
  location: string;
  detected_at: string;
  received_at: string;
  status: "active" | "acknowledged" | "resolved";
  sms_status: string;
  sms_results: Array<Record<string, string>>;
  metadata: Record<string, string | number | boolean>;
};

export type IncidentStatus = "unacknowledged" | "acknowledged" | "dispatched" | "resolved";

export type Incident = {
  id: string;
  timestamp: string;
  zone: string;
  eventType: string;
  confidence: number;
  severity: "critical" | "warning";
  status: IncidentStatus;
  smsStatus: string;
  cameraId: string;
  description: string;
  metadata: BackendIncident["metadata"];
  acknowledgedAt?: string;
  dispatchedAt?: string;
};

export type Zone = {
  id: string;
  name: string;
  status: "normal" | "warning" | "critical";
  incidentsToday: number;
};

export type CoachResult = {
  mode: "gemini" | "local_summary";
  answer: string;
  incident_ids: string[];
  context_count: number;
  truncated: boolean;
  zone_id: string | null;
};

const title = (value: string) =>
  value.split("_").map(part => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");

export function normalizeIncident(raw: BackendIncident): Incident {
  const smsDispatched = !["not_required", "pending", "cooldown", "not_configured", "failed", "unknown"].includes(raw.sms_status);
  const status: IncidentStatus =
    raw.status === "resolved" ? "resolved" :
    raw.status === "acknowledged" ? "acknowledged" :
    smsDispatched ? "dispatched" : "unacknowledged";

  return {
    id: raw.incident_id,
    timestamp: raw.detected_at,
    zone: raw.location || raw.zone_id,
    eventType: raw.event_type === "fall" ? "Worker Down" : title(raw.event_type),
    confidence: Math.round(raw.pose_confidence * 100),
    severity: raw.severity === "high" ? "critical" : "warning",
    status,
    smsStatus: raw.sms_status,
    cameraId: raw.camera_id,
    description: raw.description,
    metadata: raw.metadata,
  };
}
