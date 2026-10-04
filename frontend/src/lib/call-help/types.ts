export type Incident = {
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
  sms_results: { status: string; recipient: string }[];
  metadata: Record<string, string | number | boolean>;
};
export type CoachAnswer = {
  answer: string;
  mode: "ollama";
  incident_ids: string[];
  context_count: number;
  truncated: boolean;
};
export type Zone = { id: string; name: string; status: "normal" | "critical"; incidentsToday: number };
export const eventLabel = (kind: string) => ({ fall: "Possible fall", ppe_violation: "PPE violation", collision_risk: "Collision risk" }[kind] || kind);
export function mergeIncident(rows: Incident[], incoming: Incident): Incident[] {
  return [incoming, ...rows.filter(row => row.incident_id !== incoming.incident_id)]
    .sort((a, b) => b.detected_at.localeCompare(a.detected_at));
}
