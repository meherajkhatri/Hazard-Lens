import { initialIncidents, safetyAnalysis, type Incident } from "./mock-data";

// Replace local reads and mutations with Supabase incident APIs when available.
export function fetchIncidents(): Incident[] { return initialIncidents.map((incident) => ({ ...incident })); }
// Feed Python computer-vision WebSocket events through this same entry point.
export function handleIncomingIncident(incident: Incident): Incident { return { ...incident }; }
export function acknowledgeIncident(incident: Incident): Incident {
  return { ...incident, status: "acknowledged", acknowledgedAt: new Date().toISOString() };
}
export function dispatchResponse(incident: Incident): Incident {
  // Connect a server-side alert provider here; never expose service credentials in the client.
  return { ...incident, status: "dispatched", dispatchedAt: new Date().toISOString() };
}
export async function generateAIAnalysis() {
  // Replace with a server-side Gemini API call using recorded incident history.
  await new Promise((resolve) => setTimeout(resolve, 1000));
  return safetyAnalysis;
}
export function triggerAlertSound() {
  // Future audible alert implementation. The demo intentionally plays no audio.
}
