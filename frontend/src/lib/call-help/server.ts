// Imported only by route handlers. Never expose API_KEY as NEXT_PUBLIC_*.
export function backendUrl(path: string) {
  return `${(process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "")}${path}`;
}
export function backendHeaders() {
  return { "Content-Type": "application/json", "X-API-Key": process.env.API_KEY || "" };
}
export function sameOrigin(request: Request) {
  const origin = request.headers.get("origin");
  // Next may normalize request.url to its bind hostname. The browser uses Host.
  const expected = new URL(request.url);
  expected.host = request.headers.get("host") || expected.host;
  return !origin || origin === expected.origin;
}
