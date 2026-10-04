import { backendHeaders, backendUrl, sameOrigin } from "@/lib/call-help/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
async function proxy(request: Request, context: { params: Promise<{ path: string[] }> }) {
  if (!sameOrigin(request)) return Response.json({ detail: "Origin not allowed" }, { status: 403 });
  const { path } = await context.params;
  const resource = path.join("/");
  const allowed = (request.method === "GET" && ["incidents", "health"].includes(resource))
    || (request.method === "POST" && resource === "coach/chat")
    || (request.method === "PATCH" && /^incidents\/[0-9a-f-]{36}$/i.test(resource));
  if (!allowed) return Response.json({ detail: "Route not available" }, { status: 404 });
  try {
    const upstream = await fetch(backendUrl(resource === "health" ? "/health" : `/api/v1/${resource}`) + new URL(request.url).search, {
      method: request.method, headers: backendHeaders(), cache: "no-store",
      body: request.method === "GET" ? undefined : await request.text(),
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(40000)]),
    });
    return new Response(await upstream.text(), { status: upstream.status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ detail: "Backend unavailable. Check BACKEND_URL and the API server." }, { status: 503 });
  }
}
export { proxy as GET, proxy as POST, proxy as PATCH };
