import WebSocket from "ws";
import { backendUrl, sameOrigin } from "@/lib/call-help/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Bridge the authenticated backend WebSocket to a same-origin EventSource.
// The browser never receives the backend key. EventSource retries automatically;
// the dashboard refreshes its REST snapshot after every connection.
export function GET(request: Request) {
  if (!sameOrigin(request)) return new Response("Origin not allowed", { status: 403 });
  let cleanup = () => {};
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      const url = new URL(backendUrl("/ws/incidents"));
      url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
      const socket = new WebSocket(url, { handshakeTimeout: 5000 });
      let ended = false;
      const heartbeat = setInterval(() => {
        if (!ended) controller.enqueue(encoder.encode(": keepalive\n\n"));
      }, 15000);
      const authTimeout = setTimeout(() => finish(), 7000);
      function finish() {
        if (ended) return;
        ended = true;
        clearInterval(heartbeat);
        clearTimeout(authTimeout);
        request.signal.removeEventListener("abort", finish);
        socket.terminate();
        try { controller.close(); } catch { /* Consumer already cancelled. */ }
      }
      cleanup = finish;
      socket.on("open", () => { if (process.env.API_KEY) socket.send(JSON.stringify({ api_key: process.env.API_KEY })); });
      socket.on("message", raw => {
        if (ended) return;
        try {
          const event = JSON.parse(raw.toString());
          if (event.type === "connected") clearTimeout(authTimeout);
          if (["connected", "incident.created", "incident.updated"].includes(event.type)) {
            // Disconnect slow consumers; reconnect triggers a fresh snapshot.
            if ((controller.desiredSize ?? 0) < -100) return finish();
            controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`));
          }
        } catch { finish(); }
      });
      socket.on("close", finish);
      socket.on("error", finish);
      request.signal.addEventListener("abort", finish, { once: true });
      if (request.signal.aborted) finish();
    },
    cancel() { cleanup(); },
  });
  return new Response(stream, { headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no" } });
}
