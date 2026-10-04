export type CameraPerson = {
  track_id: number;
  bbox: [number, number, number, number];
  state: "upright" | "falling" | "down";
  confidence: number;
};

export type DetectionResult = {
  success: boolean;
  person_detected: boolean;
  fall_detected: boolean;
  confidence: number;
  status: "normal" | "person_detected" | "possible_fall" | "fall_detected";
  people: CameraPerson[];
  frame: { width: number; height: number };
  inference_ms: number;
  emergency_mode: boolean;
  simulated?: boolean;
};

export type CvHealth = {
  status: "ok" | "degraded";
  model_ready: boolean;
  model: string;
  device: string;
  emergency_mode: boolean;
  test_mode: boolean;
  confirmation_seconds: number;
  confidence_threshold: number;
  last_inference_ms: number;
  error?: string | null;
};

const CV_URL = (process.env.NEXT_PUBLIC_CV_API_URL || "http://127.0.0.1:5000").replace(/\/$/, "");

export async function getCvHealth(signal?: AbortSignal): Promise<CvHealth> {
  const response = await fetch(`${CV_URL}/api/health`, { cache: "no-store", signal });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || data.error === "" ? data.error : "CV backend unavailable");
  return data as CvHealth;
}

export async function detectFrame(frame: Blob, zoneId: string, signal?: AbortSignal): Promise<DetectionResult> {
  const body = new FormData();
  body.append("frame", frame, "frame.jpg");
  body.append("zone_id", zoneId);
  const response = await fetch(`${CV_URL}/api/detect`, { method: "POST", body, signal });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Detection failed (${response.status})`);
  return data as DetectionResult;
}

export async function simulateFall(zoneId: string): Promise<DetectionResult> {
  const body = new FormData();
  body.append("zone_id", zoneId);
  const response = await fetch(`${CV_URL}/api/test/fall`, { method: "POST", body });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "Safe fall simulation unavailable");
  return data as DetectionResult;
}
