import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Vite config: dev server proxies REST + WebSocket to Django so the
// frontend can use relative URLs (`/api/...`, `/ws/...`) in both dev
// and prod.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://localhost:8000",
        ws: true,
        changeOrigin: true,
      },
      "/admin": "http://localhost:8000",
      "/static": "http://localhost:8000",
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
