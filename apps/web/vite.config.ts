import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // FAIL rather than drift. Without this, a Vite told to take a different port
    // — or one whose --port argument was silently swallowed, which pnpm 10 does
    // to `pnpm run <script> -- --port N` — falls back to 5173 and reports
    // nothing. That stray 5173 is exactly what the next `just e2e` reuses
    // (`reuseExistingServer: true`), pointing it at a torn-down gateway, so every
    // spec 500s at seedSession and reads as a code regression. An agent booting
    // an ISOLATED frontend must get a loud failure, not the shared port.
    strictPort: true,
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
