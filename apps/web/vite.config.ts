import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // The web app talks ONLY to the gateway (CLAUDE.md service boundaries).
    // The origin defaults to the shared dev gateway; GATEWAY_ORIGIN overrides it
    // so an isolated stack (e.g. e2e on ports 8010–8012) can be driven without
    // disturbing the shared :8000 gateway.
    proxy: {
      "/api": {
        target: process.env["GATEWAY_ORIGIN"] ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
