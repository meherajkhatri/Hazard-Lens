import { BackendIncident, CoachResult, Incident, normalizeIncident } from "./types";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const WS_URL = API_URL.replace(/^http/, "ws");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${response.status})`);
  }
  return response.json();
}

export async function getHealth() {
  return request<{ status: string; storage: string; sms_mode: string; coach_mode: string }>("/health");
}

export async function getIncidents(): Promise<Incident[]> {
  const rows = await request<BackendIncident[]>("/api/v1/incidents?limit=100");
  return rows.map(normalizeIncident);
}

export async function setIncidentStatus(id: string, status: "acknowledged" | "resolved"): Promise<Incident> {
  const row = await request<BackendIncident>(`/api/v1/incidents/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
  return normalizeIncident(row);
}

export async function sendDemoFall(zoneId = "Forklift Corridor 1") {
  return request<{ status: string; incident?: BackendIncident }>("/api/v1/telemetry", {
    method: "POST",
    body: JSON.stringify({
      camera_id: "demo-cam-01",
      zone_id: zoneId,
      timestamp: new Date().toISOString(),
      event_type: "fall",
      pose_confidence: 0.94,
      metadata: { source: "frontend_demo" },
    }),
  });
}

export async function askSafetyCoach(question: string, zoneId?: string): Promise<CoachResult> {
  return request<CoachResult>("/api/v1/coach/chat", {
    method: "POST",
    body: JSON.stringify({ question, zone_id: zoneId || null }),
  });
}

export function connectIncidentSocket(onIncident: (incident: Incident) => void, onState: (connected: boolean) => void) {
  const socket = new WebSocket(`${WS_URL}/ws/incidents`);
  socket.onopen = () => onState(true);
  socket.onclose = () => onState(false);
  socket.onerror = () => onState(false);
  socket.onmessage = event => {
    try {
      const message = JSON.parse(event.data);
      if ((message.type === "incident.created" || message.type === "incident.updated") && message.incident) {
        onIncident(normalizeIncident(message.incident as BackendIncident));
      }
    } catch {
      // REST refresh remains available if a malformed realtime event arrives.
    }
  };
  return () => socket.close();
}
