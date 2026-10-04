export type Incident = {
  id: string;
  timestamp: string;
  zone: string;
  eventType: string;
  confidence: number;
  severity: "low" | "warning" | "critical";
  status: "unacknowledged" | "acknowledged" | "dispatched" | "resolved";
  acknowledgedAt?: string;
  dispatchedAt?: string;
};

export type Zone = {
  id: string;
  name: string;
  status: "normal" | "warning" | "critical";
  incidentsToday: number;
};

export const initialZones: Zone[] = [
  { id: "01", name: "Loading Dock", status: "normal", incidentsToday: 0 },
  { id: "02", name: "Forklift Corridor 1", status: "normal", incidentsToday: 1 },
  { id: "03", name: "AGV Corridor", status: "normal", incidentsToday: 0 },
  { id: "04", name: "Assembly Crossing", status: "normal", incidentsToday: 0 },
];

export const initialIncidents: Incident[] = [
  { id: "INC-042", timestamp: "2026-10-03T14:31:18", zone: "Forklift Corridor 1", eventType: "Worker Down", confidence: 94, severity: "critical", status: "resolved" },
  { id: "INC-041", timestamp: "2026-10-03T13:42:00", zone: "Loading Ramp", eventType: "Near Fall", confidence: 89, severity: "warning", status: "acknowledged" },
  { id: "INC-040", timestamp: "2026-10-03T11:18:00", zone: "AGV Corridor", eventType: "Transit Obstruction", confidence: 96, severity: "low", status: "resolved" },
  { id: "INC-039", timestamp: "2026-10-03T09:52:00", zone: "Forklift Corridor 1", eventType: "Near Fall", confidence: 91, severity: "warning", status: "resolved" },
];

export const hourlyData = [
  { hour: "8 AM", incidents: 0 }, { hour: "10 AM", incidents: 1 },
  { hour: "12 PM", incidents: 0 }, { hour: "2 PM", incidents: 2 },
  { hour: "4 PM", incidents: 3 }, { hour: "6 PM", incidents: 1 },
];
export const initialStats = { incidents: 3, falls: 1, nearFalls: 2, response: "4.2" };
export const safetyAnalysis = {
  summary: "Forklift Corridor 1 shows the highest concentration of recorded incidents during afternoon transit activity.",
  detail: "5 of the last 7 incidents occurred between 2 PM and 5 PM. Several events were recorded near Loading Ramp 3.",
  recommendations: ["Inspect pedestrian and forklift separation near Loading Ramp 3", "Review afternoon traffic flow", "Inspect flooring and visibility conditions", "Consider additional warning signage"],
};
