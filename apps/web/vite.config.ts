import { execSync } from "node:child_process";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/**
 * The commit this bundle was built from, injected at build time.
 *
 * WHY THIS EARNS ITS KEEP (FB-11, founder 2026-08-01): the founder tests from a
 * GitHub Codespace, so a bug report cannot be tied to a commit and "already
 * fixed, or still broken?" is unanswerable from either side. Two fixes landed
 * mid-session and neither of us could say whether the last report included
 * them — which is a whole class of wasted round trip, not a nicety.
 *
 * Falls back to "unknown" rather than throwing: a tarball with no .git is a
 * legitimate way to build this app, and a build stamp is never worth failing a
 * build over. `unknown` is also honest — it says we cannot tell, which is
 * exactly the state it reports.
 */
function buildStamp(): { sha: string; time: string } {
  let sha = "unknown";
  try {
    sha = execSync("git rev-parse --short HEAD", {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
    const dirty = execSync("git status --porcelain", {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
    // A dirty tree is a DIFFERENT artifact from the commit it sits on, and
    // saying so is the whole point — an unmarked local build reported as a
    // clean SHA is worse than "unknown".
    if (dirty !== "") sha = `${sha}-dirty`;
  } catch {
    /* no git (tarball / container build) — "unknown" is the honest answer */
  }
  return { sha, time: new Date().toISOString() };
}

const build = buildStamp();

export default defineConfig({
  define: {
    __BUILD_SHA__: JSON.stringify(build.sha),
    __BUILD_TIME__: JSON.stringify(build.time),
  },
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
