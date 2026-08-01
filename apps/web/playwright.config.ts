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
    // On failure only, so a red CI shard arrives with evidence instead of a
    // stack trace. This suite has never executed on a hosted runner before the
    // e2e workflow landed, and several specs assert on CANVAS PIXELS — if
    // software-GL rendering differs there, a trace shows the actual frame and a
    // bare assertion message does not. Written into test-results/ (gitignored,
    // uploaded as an artifact by .github/workflows/e2e.yml); nothing is written
    // when a test passes, so a green run stays free and the tree stays clean.
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
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
    // `--host 127.0.0.1` is load-bearing, not tidiness. Vite forces
    // dns.setDefaultResultOrder("verbatim"), so on a DUAL-STACK host its
    // default host `localhost` can resolve to ::1 first and Vite then listens
    // on ::1 only — while `url` and `baseURL` here are literal 127.0.0.1. The
    // process stays alive and simply never answers, which is exactly the shape
    // the first e2e-workflow runs hit on GitHub runners: "Timed out waiting
    // 60000ms from config.webServer", NOT "exited early". It cannot reproduce
    // in the dev container, which has no IPv6 loopback at all, so binding the
    // literal IPv4 loopback is how the ambiguity stops mattering either way.
    command: "pnpm dev --host 127.0.0.1 --strictPort",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: true,
    // 60_000 was a warm-laptop number. Measured here with the dep cache
    // DELETED: 1.3 s to index.html, 5.5 s to the entry module — so cold
    // pre-bundling was never the problem and this is not a fix, it is headroom
    // so a slow shared runner cannot turn a working stack into an opaque
    // timeout. It costs nothing on a server that comes up.
    timeout: 180_000,
    // Without these Playwright discards Vite's output, so a webServer failure
    // arrives as a bare timeout naming no cause — which is precisely why the
    // first CI failure cost a full round trip to diagnose.
    stdout: "pipe",
    stderr: "pipe",
  },
});
