import type { CoachAnswer, Incident } from "./types";

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/backend/${path}`, {
    ...init, cache: "no-store", signal: init?.signal ?? AbortSignal.timeout(45000),
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : `Request failed (${response.status})`);
  return data as T;
}
export async function fetchIncidents(signal?: AbortSignal) {
  const rows: Incident[] = [];
  for (let offset = 0; ; offset += 500) {
    const page = await request<Incident[]>(`incidents?limit=500&offset=${offset}`, { signal });
    rows.push(...page);
    if (page.length < 500) return rows;
  }
}
export const updateIncident = (id: string, status: "acknowledged" | "resolved") =>
  request<Incident>(`incidents/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify({ status }) });
export const askCoach = (question: string, zone_id?: string) =>
  request<CoachAnswer>("coach/chat", { method: "POST", body: JSON.stringify({ question, ...(zone_id ? { zone_id } : {}) }) });
