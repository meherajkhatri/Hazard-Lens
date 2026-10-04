import type { NextConfig } from "next";

// ws reads these when it loads. Setting them here (not in the npm scripts)
// keeps `npm run dev` working on Windows as well as macOS/Linux.
process.env.WS_NO_BUFFER_UTIL ??= "1";
process.env.WS_NO_UTF_8_VALIDATE ??= "1";

// LAN addresses other devices use to open the dev server, comma-separated
// (e.g. ALLOWED_DEV_ORIGINS=35.7.249.20). Next blocks dev requests from unlisted ones.
const allowedDevOrigins = (process.env.ALLOWED_DEV_ORIGINS || "35.7.254.198")
  .split(",").map(host => host.trim()).filter(Boolean);

const nextConfig: NextConfig = {
  allowedDevOrigins,
};

export default nextConfig;
