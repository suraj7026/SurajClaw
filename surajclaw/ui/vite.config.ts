import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Where the dev server forwards API + WebSocket traffic. Defaults to the
// host's Django on 8000. In docker-compose the `ui` container sets this to
// `http://web:8000` so it can resolve the sibling service over the compose
// network.
const PROXY_TARGET = process.env.VITE_PROXY_TARGET ?? "http://localhost:8000";
const WS_TARGET = PROXY_TARGET.replace(/^http/, "ws");

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    host: true,
    port: 5173,
    strictPort: false,
    proxy: {
      "/api": { target: PROXY_TARGET, changeOrigin: true },
      "/ws": { target: WS_TARGET, ws: true, changeOrigin: true },
      "/admin": PROXY_TARGET,
      "/static": PROXY_TARGET,
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
