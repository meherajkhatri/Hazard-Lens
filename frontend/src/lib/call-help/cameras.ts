export type CameraStreams = Record<string, string>;

const DEFAULT_CV_STREAM = "http://127.0.0.1:8001/stream";

export function parseCameraStreams(value: string | undefined): CameraStreams {
  if (!value) return {};
  try {
    const parsed: unknown = JSON.parse(value);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    return Object.fromEntries(Object.entries(parsed).filter(([, url]) =>
      typeof url === "string" && /^https?:\/\//.test(url),
    ));
  } catch {
    return {};
  }
}

export function resolveCameraStream(cameraId: string | null, legacyStream?: string): string {
  const streams = parseCameraStreams(process.env.NEXT_PUBLIC_CAMERA_STREAMS);
  if (cameraId && streams[cameraId]) return streams[cameraId];
  return legacyStream || process.env.NEXT_PUBLIC_CAMERA_STREAM_URL || DEFAULT_CV_STREAM;
}

export function resolveCameraHealth(streamUrl: string): string {
  try {
    const url = new URL(streamUrl);
    url.pathname = "/health";
    url.search = "";
    url.hash = "";
    return url.toString();
  } catch {
    return "http://127.0.0.1:8001/health";
  }
}
