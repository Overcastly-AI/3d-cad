import { defineConfig } from "@playwright/test";

/**
 * First-light e2e: drives the real stack. Requires the geometry service
 * (:8002) and gateway (:8000) to be running — see README. The Vite dev
 * server is started automatically.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  use: {
    baseURL: "http://127.0.0.1:5173",
    viewport: { width: 1600, height: 1000 },
    deviceScaleFactor: 1,
    // Portable, low-noise rendering for deliberate screenshot refreshes
    // (UPDATE_SCREENSHOTS=1). Software GL + fixed colour profile + no font
    // hinting + grayscale AA make a refresh's diff machine-independent and
    // minimal, so any contributor regenerates near-identical founder shots.
    // (Byte-exactness across a full run still isn't guaranteed by Chromium, which
    // is why routine runs gate the file write — see e2e/fixtures.ts.)
    launchOptions: {
      args: [
        "--disable-gpu",
        "--force-color-profile=srgb",
        "--font-render-hinting=none",
        "--disable-lcd-text",
        "--disable-skia-runtime-opts",
      ],
    },
  },
  webServer: {
    command: "pnpm dev --strictPort",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
