export type CameraStreams = Record<string, string>;
export type Camera = { id: string; zone: string; stream: string };

function parseObject(value: string | undefined): Record<string, unknown> {
  try {
    const parsed: unknown = JSON.parse(value || "{}");
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {};
  } catch { return {}; }
}

export function imageUrl(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password ? url.href : undefined;
  } catch { return undefined; }
}

export function parseCameraStreams(value: string | undefined): CameraStreams {
  return Object.fromEntries(Object.entries(parseObject(value)).flatMap(([id, value]) => {
    const url = imageUrl(value);
    return id.trim() && url ? [[id, url]] : [];
  }));
}

export function configuredCameras(): Camera[] {
  const streams = parseCameraStreams(process.env.NEXT_PUBLIC_CAMERA_STREAMS);
  const zones = parseObject(process.env.NEXT_PUBLIC_CAMERA_ZONES);
  const legacyId = process.env.NEXT_PUBLIC_CAMERA_ID || "zone-1-cam-1";
  const legacyZone = process.env.NEXT_PUBLIC_CAMERA_ZONE || "Zone 1";
  const legacyStream = imageUrl(process.env.NEXT_PUBLIC_CAMERA_STREAM_URL);
  if (legacyStream && !streams[legacyId]) streams[legacyId] = legacyStream;
  return Object.entries(streams).map(([id, stream]) => ({ id, stream,
    zone: typeof zones[id] === "string" ? zones[id] as string : legacyZone }));
}

export function resolveCameraStream(cameraId: string | null, legacyStream?: string,
  legacyCameraId = process.env.NEXT_PUBLIC_CAMERA_ID || "zone-1-cam-1"): string | undefined {
  const streams = parseCameraStreams(process.env.NEXT_PUBLIC_CAMERA_STREAMS);
  if (cameraId && Object.hasOwn(streams, cameraId)) return streams[cameraId];
  // Never show another camera's pixels under the incident camera's label.
  return !cameraId || cameraId === legacyCameraId ? imageUrl(legacyStream) : undefined;
}
