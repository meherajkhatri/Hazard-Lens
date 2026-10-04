export type CameraStreams = Record<string, string>;

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

export function resolveCameraStream(cameraId: string | null, legacyStream?: string): string | undefined {
  const streams = parseCameraStreams(process.env.NEXT_PUBLIC_CAMERA_STREAMS);
  if (cameraId && streams[cameraId]) return streams[cameraId];
  return legacyStream;
}
